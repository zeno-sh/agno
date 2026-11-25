"""Offline tests for the employee /v1 cloud-session gateway."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from v1_gateway import create_v1_app  # noqa: E402


class _FakeAgent:
    def __init__(self, agent_id: str, name: str, description: str) -> None:
        self.id = agent_id
        self.name = name
        self.description = description
        self.prompts: list[tuple[str, str | None]] = []

    async def arun(self, prompt: str, *, session_id: str | None = None, **kwargs):
        self.prompts.append((prompt, session_id))

        async def _gen():
            yield SimpleNamespace(event="RunStarted")
            await asyncio.sleep(0.01)
            yield SimpleNamespace(event="ToolCallStarted")
            await asyncio.sleep(0.01)
            yield SimpleNamespace(event="RunContent", content="计算结果：")
            yield SimpleNamespace(event="RunContent", content="(0.1+0.2)*10 = 3")
            yield SimpleNamespace(event="RunCompleted", content="计算结果：(0.1+0.2)*10 = 3")

        return _gen()


def test_v1_gateway_full_lifecycle(tmp_path: Path) -> None:
    fake_calc = _FakeAgent("calculator-agent", "计算器", "十进制四则表达式计算")
    fake_http = _FakeAgent("http-info-agent", "HTTP 查询（地震目录）", "地震查询")
    app = create_v1_app(
        agents=[fake_calc, fake_http],
        employee_token="test-token-123",
        data_dir=tmp_path,
        employee_id="mvp-jax",
        display_name="Jax",
    )
    headers = {"Authorization": "Bearer test-token-123"}

    with TestClient(app) as client:
        # Health is open; legacy /agents is closed; /v1 requires bearer token.
        assert client.get("/health").status_code == 200
        assert client.get("/agents").status_code == 404
        assert client.get("/v1/skills").status_code == 401

        # Identity & skills
        me = client.get("/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json() == {"employee_id": "mvp-jax", "display_name": "Jax"}

        skills_res = client.get("/v1/skills", headers=headers)
        assert skills_res.status_code == 200
        skills = skills_res.json()["skills"]
        assert [s["id"] for s in skills] == ["calculator-agent", "http-info-agent"]
        assert skills[0]["input_schema"]["required"] == ["expression"]

        # Create conversation
        conv_res = client.post(
            "/v1/conversations",
            headers=headers,
            json={"skill_id": "calculator-agent"},
        )
        assert conv_res.status_code == 201
        conv_id = conv_res.json()["id"]

        # Round 1 missing mandatory expression -> 422 invalid_input with field
        bad_turn = client.post(
            f"/v1/conversations/{conv_id}/turns",
            headers=headers,
            json={"message": "算一下", "inputs": {}, "attachment_ids": []},
        )
        assert bad_turn.status_code == 422
        assert bad_turn.json()["error"]["field"] == "expression"

        # Round 1 valid + Idempotency-Key replay
        idem_headers = {**headers, "Idempotency-Key": "idem-round-1"}
        turn_res = client.post(
            f"/v1/conversations/{conv_id}/turns",
            headers=idem_headers,
            json={
                "message": "只给结果",
                "inputs": {"expression": "(0.1+0.2)*10"},
                "attachment_ids": [],
            },
        )
        assert turn_res.status_code == 202
        turn_id = turn_res.json()["id"]

        replay_res = client.post(
            f"/v1/conversations/{conv_id}/turns",
            headers=idem_headers,
            json={
                "message": "只给结果",
                "inputs": {"expression": "(0.1+0.2)*10"},
                "attachment_ids": [],
            },
        )
        assert replay_res.status_code == 200
        assert replay_res.json()["id"] == turn_id

        # Follow SSE until terminal
        sse_text = ""
        with client.stream("GET", f"/v1/turns/{turn_id}/events", headers=headers) as stream:
            assert stream.status_code == 200
            for chunk in stream.iter_text():
                sse_text += chunk
        assert "event: stage" in sse_text
        assert "event: delta" in sse_text
        assert "(0.1+0.2)*10 = 3" in sse_text
        assert "event: terminal" in sse_text

        # Round 2 follow-up with empty inputs succeeds (required only on Round 1)
        round2 = client.post(
            f"/v1/conversations/{conv_id}/turns",
            headers={**headers, "Idempotency-Key": "idem-round-2"},
            json={"message": "把结果乘以 2", "inputs": {}, "attachment_ids": []},
        )
        assert round2.status_code == 202
        round2_id = round2.json()["id"]
        with client.stream("GET", f"/v1/turns/{round2_id}/events", headers=headers) as stream:
            list(stream.iter_text())

        # Conversation detail persists both turns
        detail = client.get(f"/v1/conversations/{conv_id}", headers=headers)
        assert detail.status_code == 200
        assert len(detail.json()["turns"]) == 2
        assert detail.json()["turns"][0]["answer"] == "计算结果：(0.1+0.2)*10 = 3"
        assert fake_calc.prompts[0][1] == conv_id
        assert fake_calc.prompts[1][1] == conv_id

    app.state.v1_store.close()
