"""Company /v1 cloud-session product API over Agno skill agents.

Exposes only the authenticated /v1 product endpoints required by the client
plugin (me, skills, conversations, turns, SSE events with Last-Event-ID replay,
cancel, awaiting-input hook, uploads, and artifact downloads). Internal AgentOS
routes (/agents, /sessions) stay off the employee listener.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
SAFE_FILENAME_RE = re.compile(r"[\x00-\x1f\x7f<>:\"|?*\\/]+")

# Product metadata overlays for published script agents.
SKILL_METADATA_OVERRIDES: dict[str, dict[str, Any]] = {
    "calculator-agent": {
        "version": "1.0.0",
        "category": "通用",
        "egress": "byok_allowed",
        "attachments": None,
        "input_schema": {
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {
                    "type": "string",
                    "title": "四则表达式",
                    "description": "十进制四则表达式，1–160 个字符，支持括号及正负号，例如 (0.1+0.2)*10",
                    "minLength": 1,
                    "maxLength": 160,
                }
            },
        },
    },
    "http-info-agent": {
        "version": "1.0.0",
        "category": "市场",
        "egress": "byok_allowed",
        "attachments": None,
        "input_schema": {
            "type": "object",
            "required": ["latitude", "longitude"],
            "properties": {
                "latitude": {
                    "type": "number",
                    "title": "纬度",
                    "description": "纬度，-90 至 90，例如 35.68",
                    "minimum": -90,
                    "maximum": 90,
                },
                "longitude": {
                    "type": "number",
                    "title": "经度",
                    "description": "经度，-180 至 180，例如 139.69",
                    "minimum": -180,
                    "maximum": 180,
                },
            },
        },
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_filename(raw: str) -> str:
    leaf = raw.replace("\\", "/").split("/")[-1]
    cleaned = SAFE_FILENAME_RE.sub("_", leaf).lstrip(".").strip()
    return (cleaned or "artifact.bin")[:180]


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    field: str | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
        "request_id": str(uuid4()),
    }
    if field is not None:
        payload["field"] = field
    return JSONResponse({"error": payload}, status_code=status_code)


def _project_skill_spec(agent: Any) -> dict[str, Any]:
    agent_id = str(getattr(agent, "id", "") or getattr(agent, "name", "unknown"))
    override = SKILL_METADATA_OVERRIDES.get(agent_id, {})
    return {
        "id": agent_id,
        "version": str(override.get("version", "1.0.0")),
        "name": str(getattr(agent, "name", None) or agent_id),
        "description": str(getattr(agent, "description", None) or ""),
        "category": str(override.get("category", "通用")),
        "egress": str(override.get("egress", "byok_allowed")),
        "input_schema": override.get(
            "input_schema", {"type": "object", "required": [], "properties": {}}
        ),
        "attachments": override.get("attachments", None),
    }


def validate_inputs(
    schema: dict[str, Any],
    inputs: dict[str, Any] | None,
    *,
    require_mandatory: bool,
) -> str | None:
    """Validate structured JSON turn inputs against published skill input_schema."""
    actual = inputs if isinstance(inputs, dict) else {}
    required = schema.get("required") or []
    properties = schema.get("properties") or {}

    if require_mandatory:
        for req_key in required:
            val = actual.get(req_key)
            if val is None or val == "":
                return str(req_key)

    for key, val in actual.items():
        prop = properties.get(key)
        if not isinstance(prop, dict) or val is None:
            continue
        prop_type = prop.get("type")
        if prop_type == "string":
            if not isinstance(val, str):
                return str(key)
            min_len = prop.get("minLength")
            max_len = prop.get("maxLength")
            if isinstance(min_len, int) and len(val) < min_len:
                return str(key)
            if isinstance(max_len, int) and len(val) > max_len:
                return str(key)
        elif prop_type in ("number", "integer"):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return str(key)
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if isinstance(minimum, (int, float)) and val < minimum:
                return str(key)
            if isinstance(maximum, (int, float)) and val > maximum:
                return str(key)
    return None


def format_agent_prompt(
    skill_spec: dict[str, Any],
    message: str,
    inputs: dict[str, str | int | float],
) -> str:
    """Compose natural-language prompt combining structured parameters and user note."""
    properties = (skill_spec.get("input_schema") or {}).get("properties") or {}
    lines: list[str] = []
    for key, val in inputs.items():
        prop = properties.get(key)
        title = prop.get("title") if isinstance(prop, dict) else None
        label = str(title or key)
        lines.append(f"{label}：{val}")
    trimmed = message.strip()
    if lines and trimmed:
        return "\n".join(lines) + "\n\n" + trimmed
    if lines:
        return "\n".join(lines)
    return trimmed or "请按默认参数执行。"


class V1Store:
    """SQLite-backed durable store for /v1 conversations, turns, events, and artifacts."""

    def __init__(self, db_path: Path, artifacts_dir: Path) -> None:
        self.db_path = db_path
        self.artifacts_dir = artifacts_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._recover_interrupted_turns()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    skill_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_turn_status TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    attachments_json TEXT NOT NULL,
                    answer TEXT,
                    artifacts_json TEXT NOT NULL,
                    egress TEXT NOT NULL,
                    pending_input_json TEXT,
                    error_json TEXT,
                    idempotency_key TEXT,
                    request_fingerprint TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_turns_conv_created ON turns (conversation_id, created_at)"
            )
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_conv_idem
                ON turns (conversation_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turn_events (
                    turn_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (turn_id, seq)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    egress TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _recover_interrupted_turns(self) -> None:
        """Mark any turns left active across a server restart as failed."""
        error_json = json.dumps(
            {
                "code": "unavailable",
                "message": "服务重启导致本次运行中断，请重试。",
                "retryable": True,
            },
            ensure_ascii=False,
        )
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, conversation_id FROM turns WHERE status IN ('queued', 'running', 'cancel_requested')"
            ).fetchall()
            for row in rows:
                self._conn.execute(
                    "UPDATE turns SET status = 'failed', error_json = ? WHERE id = ?",
                    (error_json, row["id"]),
                )
                self._conn.execute(
                    "UPDATE conversations SET last_turn_status = 'failed' WHERE id = ?",
                    (row["conversation_id"],),
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _row_to_turn(self, row: sqlite3.Row) -> dict[str, Any]:
        turn: dict[str, Any] = {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "status": row["status"],
            "message": row["message"],
            "inputs": json.loads(row["inputs_json"]),
            "attachments": json.loads(row["attachments_json"]),
            "artifacts": json.loads(row["artifacts_json"]),
            "egress": row["egress"],
            "created_at": row["created_at"],
        }
        if row["answer"] is not None:
            turn["answer"] = row["answer"]
        if row["pending_input_json"] is not None:
            turn["pending_input"] = json.loads(row["pending_input_json"])
        if row["error_json"] is not None:
            turn["error"] = json.loads(row["error_json"])
        return turn

    def create_conversation(
        self, employee_id: str, skill_spec: dict[str, Any]
    ) -> dict[str, Any]:
        conv_id = f"conv-{uuid4()}"
        now = _utc_now_iso()
        title = str(skill_spec["name"])
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO conversations (id, employee_id, skill_id, skill_version, title, updated_at, last_turn_status)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (conv_id, employee_id, skill_spec["id"], skill_spec["version"], title, now),
            )
        return {
            "id": conv_id,
            "skill_id": skill_spec["id"],
            "skill_version": skill_spec["version"],
            "title": title,
            "updated_at": now,
            "turns": [],
        }

    def list_conversations(
        self, employee_id: str, offset: int, limit: int
    ) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, skill_id, skill_version, title, updated_at, last_turn_status
                FROM conversations
                WHERE employee_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (employee_id, limit + 1, offset),
            ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        items: list[dict[str, Any]] = []
        for row in page:
            item: dict[str, Any] = {
                "id": row["id"],
                "skill_id": row["skill_id"],
                "skill_version": row["skill_version"],
                "title": row["title"],
                "updated_at": row["updated_at"],
            }
            if row["last_turn_status"] is not None:
                item["last_turn_status"] = row["last_turn_status"]
            items.append(item)
        result: dict[str, Any] = {"conversations": items}
        if has_more:
            result["next_cursor"] = str(offset + limit)
        return result

    def get_conversation(
        self, employee_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, skill_id, skill_version, title, updated_at, last_turn_status
                FROM conversations
                WHERE id = ? AND employee_id = ?
                """,
                (conversation_id, employee_id),
            ).fetchone()
            if row is None:
                return None
            turn_rows = self._conn.execute(
                """
                SELECT * FROM turns
                WHERE conversation_id = ? AND employee_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (conversation_id, employee_id),
            ).fetchall()
        conv: dict[str, Any] = {
            "id": row["id"],
            "skill_id": row["skill_id"],
            "skill_version": row["skill_version"],
            "title": row["title"],
            "updated_at": row["updated_at"],
            "turns": [self._row_to_turn(t) for t in turn_rows],
        }
        if row["last_turn_status"] is not None:
            conv["last_turn_status"] = row["last_turn_status"]
        return conv

    def find_turn_by_idempotency(
        self, employee_id: str, conversation_id: str, idempotency_key: str
    ) -> tuple[dict[str, Any], str] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM turns
                WHERE conversation_id = ? AND employee_id = ? AND idempotency_key = ?
                """,
                (conversation_id, employee_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_turn(row), str(row["request_fingerprint"] or "")

    def create_turn(
        self,
        *,
        employee_id: str,
        conversation_id: str,
        message: str,
        inputs: dict[str, str | int | float],
        attachments: list[dict[str, Any]],
        egress: str,
        idempotency_key: str | None,
        request_fingerprint: str,
        updated_title: str | None = None,
    ) -> dict[str, Any]:
        turn_id = f"turn-{uuid4()}"
        now = _utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO turns (
                    id, conversation_id, employee_id, status, message, inputs_json,
                    attachments_json, answer, artifacts_json, egress, pending_input_json,
                    error_json, idempotency_key, request_fingerprint, created_at
                )
                VALUES (?, ?, ?, 'running', ?, ?, ?, NULL, '[]', ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    turn_id,
                    conversation_id,
                    employee_id,
                    message,
                    json.dumps(inputs, ensure_ascii=False),
                    json.dumps(attachments, ensure_ascii=False),
                    egress,
                    idempotency_key,
                    request_fingerprint,
                    now,
                ),
            )
            if updated_title:
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ?, last_turn_status = 'running', title = ? WHERE id = ?",
                    (now, updated_title, conversation_id),
                )
            else:
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ?, last_turn_status = 'running' WHERE id = ?",
                    (now, conversation_id),
                )
        return {
            "id": turn_id,
            "conversation_id": conversation_id,
            "status": "running",
            "message": message,
            "inputs": inputs,
            "attachments": attachments,
            "artifacts": [],
            "egress": egress,
            "created_at": now,
        }

    def get_turn(self, employee_id: str, turn_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM turns WHERE id = ? AND employee_id = ?",
                (turn_id, employee_id),
            ).fetchone()
        return self._row_to_turn(row) if row is not None else None

    def update_turn(
        self,
        turn_id: str,
        *,
        status: str,
        answer: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM turns WHERE id = ?", (turn_id,)
            ).fetchone()
            if row is None:
                return None
            next_answer = row["answer"] if answer is None else answer
            next_artifacts_json = (
                row["artifacts_json"]
                if artifacts is None
                else json.dumps(artifacts, ensure_ascii=False)
            )
            next_error_json = (
                None if error is None else json.dumps(error, ensure_ascii=False)
            )
            self._conn.execute(
                """
                UPDATE turns
                SET status = ?, answer = ?, artifacts_json = ?, error_json = ?, pending_input_json = NULL
                WHERE id = ?
                """,
                (status, next_answer, next_artifacts_json, next_error_json, turn_id),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ?, last_turn_status = ? WHERE id = ?",
                (now, status, row["conversation_id"]),
            )
            updated = self._conn.execute(
                "SELECT * FROM turns WHERE id = ?", (turn_id,)
            ).fetchone()
        return self._row_to_turn(updated) if updated is not None else None

    def append_event(
        self, turn_id: str, event_type: str, data: dict[str, Any]
    ) -> int:
        data_json = json.dumps(data, ensure_ascii=False)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM turn_events WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()
            next_seq = int(row["max_seq"]) + 1
            self._conn.execute(
                "INSERT INTO turn_events (turn_id, seq, event_type, data_json) VALUES (?, ?, ?, ?)",
                (turn_id, next_seq, event_type, data_json),
            )
        return next_seq

    def list_events_after(
        self, turn_id: str, after_seq: int
    ) -> list[tuple[int, str, dict[str, Any]]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT seq, event_type, data_json
                FROM turn_events
                WHERE turn_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (turn_id, after_seq),
            ).fetchall()
        return [
            (int(r["seq"]), str(r["event_type"]), json.loads(r["data_json"]))
            for r in rows
        ]

    def save_artifact(
        self,
        *,
        employee_id: str,
        filename: str,
        mime_type: str,
        raw_bytes: bytes,
        egress: str,
        version: int = 1,
        prefix: str = "att",
    ) -> dict[str, Any]:
        artifact_id = f"{prefix}-{uuid4().hex[:12]}"
        safe_name = _sanitize_filename(filename)
        storage_path = self.artifacts_dir / f"{artifact_id}-{safe_name}"
        storage_path.write_bytes(raw_bytes)
        now = _utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO artifacts (id, employee_id, filename, mime_type, bytes, version, egress, storage_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    employee_id,
                    safe_name,
                    mime_type,
                    len(raw_bytes),
                    version,
                    egress,
                    str(storage_path),
                    now,
                ),
            )
        return {
            "id": artifact_id,
            "filename": safe_name,
            "bytes": len(raw_bytes),
            "version": version,
            "egress": egress,
        }

    def get_artifact(
        self, employee_id: str, artifact_id: str
    ) -> tuple[dict[str, Any], str, Path] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM artifacts WHERE id = ? AND employee_id = ?",
                (artifact_id, employee_id),
            ).fetchone()
        if row is None:
            return None
        meta = {
            "id": row["id"],
            "filename": row["filename"],
            "bytes": int(row["bytes"]),
            "version": int(row["version"]),
            "egress": row["egress"],
        }
        return meta, str(row["mime_type"]), Path(row["storage_path"])


class _ActiveTurnState:
    def __init__(self) -> None:
        self.cancel_event = asyncio.Event()
        self.subscribers: set[asyncio.Queue[tuple[int, str, dict[str, Any]]]] = set()
        self.task: asyncio.Task[None] | None = None


def create_v1_app(
    *,
    agents: Sequence[Any],
    employee_token: str,
    data_dir: Path,
    employee_id: str = "mvp-jax",
    display_name: str = "Jax",
    instantiated_at: str | None = None,
    skill_metadata_resolver: Callable[[Any], dict[str, Any]] | None = None,
) -> FastAPI:
    """Create the FastAPI application serving only /health and authenticated /v1/* routes."""
    started_at = instantiated_at or _utc_now_iso()
    store = V1Store(data_dir / "company_v1.db", data_dir / "company_v1_artifacts")
    resolver = skill_metadata_resolver or _project_skill_spec
    agents_by_id: dict[str, Any] = {}
    skills_by_id: dict[str, dict[str, Any]] = {}
    skills_list: list[dict[str, Any]] = []
    for agent in agents:
        spec = resolver(agent)
        agents_by_id[spec["id"]] = agent
        skills_by_id[spec["id"]] = spec
        skills_list.append(spec)

    active_turns: dict[str, _ActiveTurnState] = {}

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.v1_store = store

    def _emit(turn_id: str, event_type: str, data: dict[str, Any]) -> int:
        seq = store.append_event(turn_id, event_type, data)
        active = active_turns.get(turn_id)
        if active is not None:
            for queue in list(active.subscribers):
                queue.put_nowait((seq, event_type, data))
        return seq

    def _check_auth(request: Request) -> JSONResponse | None:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return _error_response(401, "unauthenticated", "Missing bearer token")
        provided = auth[7:].strip()
        if not provided or not hmac.compare_digest(provided, employee_token):
            return _error_response(401, "unauthenticated", "Invalid bearer token")
        return None

    async def _run_turn(
        turn_id: str,
        conversation_id: str,
        skill_spec: dict[str, Any],
        agent: Any,
        prompt: str,
        state: _ActiveTurnState,
    ) -> None:
        answer_chunks: list[str] = []
        last_stage: str | None = None

        def emit_stage(stage: str) -> None:
            nonlocal last_stage
            if stage != last_stage:
                last_stage = stage
                _emit(turn_id, "stage", {"stage": stage})

        try:
            emit_stage("model")
            stream_result = agent.arun(
                prompt,
                stream=True,
                stream_events=True,
                user_id=employee_id,
                session_id=conversation_id,
                run_id=turn_id,
                add_history_to_context=True,
            )
            if inspect.isawaitable(stream_result):
                stream_result = await stream_result

            final_fallback_content: str | None = None
            async for ev in stream_result:
                if state.cancel_event.is_set():
                    break
                ev_type = str(getattr(ev, "event", "") or "")
                if ev_type in ("RunStarted", "ModelRequestStarted", "ReasoningStarted"):
                    emit_stage("model")
                elif ev_type == "ToolCallStarted":
                    emit_stage("tool")
                elif ev_type == "RunContent":
                    chunk = getattr(ev, "content", None)
                    if isinstance(chunk, str) and chunk:
                        answer_chunks.append(chunk)
                        _emit(turn_id, "delta", {"text": chunk})
                elif ev_type == "RunCompleted":
                    content = getattr(ev, "content", None)
                    if isinstance(content, str) and content:
                        final_fallback_content = content
                elif ev_type == "RunError":
                    logger.warning("Agent run error on turn %s: %s", turn_id, getattr(ev, "content", ""))
                    failed = store.update_turn(
                        turn_id,
                        status="failed",
                        error={
                            "code": "unavailable",
                            "message": "云端技能执行失败，请稍后重试。",
                            "retryable": True,
                        },
                    )
                    if failed is not None:
                        _emit(turn_id, "terminal", {"turn": failed})
                    return

            if state.cancel_event.is_set():
                cancelled = store.update_turn(turn_id, status="cancelled")
                if cancelled is not None:
                    _emit(turn_id, "terminal", {"turn": cancelled})
                return

            full_answer = "".join(answer_chunks)
            if not full_answer and final_fallback_content:
                full_answer = final_fallback_content
                _emit(turn_id, "delta", {"text": full_answer})

            succeeded = store.update_turn(
                turn_id,
                status="succeeded",
                answer=full_answer,
            )
            if succeeded is not None:
                _emit(turn_id, "terminal", {"turn": succeeded})
        except asyncio.CancelledError:
            cancelled = store.update_turn(turn_id, status="cancelled")
            if cancelled is not None:
                _emit(turn_id, "terminal", {"turn": cancelled})
        except Exception:
            logger.exception("Unhandled error during cloud turn %s", turn_id)
            failed = store.update_turn(
                turn_id,
                status="failed",
                error={
                    "code": "unavailable",
                    "message": "云端技能执行失败，请稍后重试。",
                    "retryable": True,
                },
            )
            if failed is not None:
                _emit(turn_id, "terminal", {"turn": failed})
        finally:
            active_turns.pop(turn_id, None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "instantiated_at": started_at}

    @app.get("/v1/me")
    async def get_me(request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        return JSONResponse({"employee_id": employee_id, "display_name": display_name})

    @app.get("/v1/skills")
    async def get_skills(request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        return JSONResponse({"skills": skills_list})

    @app.get("/v1/conversations")
    async def list_conversations(request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        cursor_raw = request.query_params.get("cursor")
        limit_raw = request.query_params.get("limit")
        try:
            offset = int(cursor_raw) if cursor_raw else 0
            limit = int(limit_raw) if limit_raw else 20
        except ValueError:
            return _error_response(422, "invalid_input", "Invalid pagination cursor or limit")
        offset = max(0, offset)
        limit = max(1, min(100, limit))
        return JSONResponse(store.list_conversations(employee_id, offset, limit))

    @app.post("/v1/conversations")
    async def create_conversation(request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        try:
            body = await request.json()
        except Exception:
            body = {}
        skill_id = str(body.get("skill_id", "")).strip() if isinstance(body, dict) else ""
        skill_spec = skills_by_id.get(skill_id)
        if skill_spec is None:
            return _error_response(404, "not_found", "Skill not found")
        conv = store.create_conversation(employee_id, skill_spec)
        return JSONResponse(conv, status_code=201)

    @app.get("/v1/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        conv = store.get_conversation(employee_id, conversation_id)
        if conv is None:
            return _error_response(404, "not_found", "Conversation not found")
        return JSONResponse(conv)

    @app.post("/v1/conversations/{conversation_id}/turns")
    async def submit_turn(conversation_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        conv = store.get_conversation(employee_id, conversation_id)
        if conv is None:
            return _error_response(404, "not_found", "Conversation not found")
        skill_spec = skills_by_id.get(conv["skill_id"])
        agent = agents_by_id.get(conv["skill_id"])
        if skill_spec is None or agent is None:
            return _error_response(404, "not_found", "Skill not found")

        try:
            body = await request.json()
        except Exception:
            return _error_response(422, "invalid_input", "Invalid JSON payload")
        if not isinstance(body, dict):
            return _error_response(422, "invalid_input", "Invalid JSON payload")

        message = str(body.get("message") or "")
        raw_inputs = body.get("inputs")
        inputs: dict[str, Any] = raw_inputs if isinstance(raw_inputs, dict) else {}
        raw_att_ids = body.get("attachment_ids")
        att_ids = [str(x) for x in raw_att_ids] if isinstance(raw_att_ids, list) else []

        fingerprint = hashlib.sha256(
            json.dumps(
                {"message": message, "inputs": inputs, "attachment_ids": att_ids},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        idem_key = request.headers.get("idempotency-key")
        if idem_key:
            existing = store.find_turn_by_idempotency(employee_id, conversation_id, idem_key)
            if existing is not None:
                existing_turn, existing_fp = existing
                if existing_fp == fingerprint:
                    return JSONResponse(existing_turn, status_code=200)
                return _error_response(409, "conflict", "Idempotency key mismatch")

        is_first_turn = len(conv["turns"]) == 0
        bad_field = validate_inputs(
            skill_spec["input_schema"], inputs, require_mandatory=is_first_turn
        )
        if bad_field is not None:
            return _error_response(422, "invalid_input", "Invalid input field", field=bad_field)

        attachments_meta: list[dict[str, Any]] = []
        if att_ids:
            rule = skill_spec.get("attachments")
            if not rule or len(att_ids) > int(rule.get("max_count", 0)):
                return _error_response(422, "invalid_input", "Attachments not allowed for skill")
            for att_id in att_ids:
                found = store.get_artifact(employee_id, att_id)
                if found is None:
                    return _error_response(422, "invalid_input", "Attachment not found")
                attachments_meta.append(found[0])

        normalized_inputs: dict[str, str | int | float] = {
            str(k): v
            for k, v in inputs.items()
            if not isinstance(v, bool) and isinstance(v, (str, int, float))
        }

        updated_title: str | None = None
        if is_first_turn:
            snippet = message.strip() or (
                str(next(iter(normalized_inputs.values()))) if normalized_inputs else ""
            )
            if snippet:
                updated_title = f"{skill_spec['name']} · {snippet[:32]}"

        turn = store.create_turn(
            employee_id=employee_id,
            conversation_id=conversation_id,
            message=message,
            inputs=normalized_inputs,
            attachments=attachments_meta,
            egress=skill_spec["egress"],
            idempotency_key=idem_key,
            request_fingerprint=fingerprint,
            updated_title=updated_title,
        )
        state = _ActiveTurnState()
        active_turns[turn["id"]] = state
        prompt = format_agent_prompt(skill_spec, message, normalized_inputs)
        state.task = asyncio.create_task(
            _run_turn(turn["id"], conversation_id, skill_spec, agent, prompt, state)
        )
        return JSONResponse(turn, status_code=202)

    @app.get("/v1/turns/{turn_id}")
    async def get_turn(turn_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        turn = store.get_turn(employee_id, turn_id)
        if turn is None:
            return _error_response(404, "not_found", "Turn not found")
        return JSONResponse({"turn": turn})

    @app.get("/v1/turns/{turn_id}/events")
    async def follow_turn_events(turn_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        turn = store.get_turn(employee_id, turn_id)
        if turn is None:
            return _error_response(404, "not_found", "Turn not found")

        last_event_id_raw = request.headers.get("last-event-id")
        after_seq = 0
        if last_event_id_raw is not None and last_event_id_raw.strip() != "":
            try:
                after_seq = int(last_event_id_raw.strip())
                if after_seq < 0:
                    raise ValueError
            except ValueError:
                return _error_response(410, "EVENT_CURSOR_EXPIRED", "Invalid event cursor")

        queue: asyncio.Queue[tuple[int, str, dict[str, Any]]] = asyncio.Queue()
        active = active_turns.get(turn_id)
        if active is not None:
            active.subscribers.add(queue)

        async def event_stream():
            last_sent = after_seq
            try:
                for seq, ev_type, data in store.list_events_after(turn_id, last_sent):
                    last_sent = seq
                    yield f"id: {seq}\nevent: {ev_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    if ev_type == "terminal":
                        return

                current = store.get_turn(employee_id, turn_id)
                if current is not None and current["status"] in TERMINAL_STATUSES:
                    # Drain any events committed between initial replay and terminal transition.
                    for seq, ev_type, data in store.list_events_after(turn_id, last_sent):
                        last_sent = seq
                        yield f"id: {seq}\nevent: {ev_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        if ev_type == "terminal":
                            return
                    yield f"event: terminal\ndata: {json.dumps({'turn': current}, ensure_ascii=False)}\n\n"
                    return

                while True:
                    try:
                        seq, ev_type, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            return
                        if turn_id not in active_turns:
                            latest = store.get_turn(employee_id, turn_id)
                            if latest is not None and latest["status"] in TERMINAL_STATUSES:
                                yield f"event: terminal\ndata: {json.dumps({'turn': latest}, ensure_ascii=False)}\n\n"
                                return
                        yield ": keepalive\n\n"
                        continue
                    if seq <= last_sent:
                        continue
                    last_sent = seq
                    yield f"id: {seq}\nevent: {ev_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    if ev_type == "terminal":
                        return
            finally:
                if active is not None:
                    active.subscribers.discard(queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/v1/turns/{turn_id}/cancel")
    async def cancel_turn(turn_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        turn = store.get_turn(employee_id, turn_id)
        if turn is None:
            return _error_response(404, "not_found", "Turn not found")
        if turn["status"] in TERMINAL_STATUSES:
            return JSONResponse(turn, status_code=200)

        updated = store.update_turn(turn_id, status="cancel_requested")
        active = active_turns.get(turn_id)
        if active is not None:
            active.cancel_event.set()
            conv = store.get_conversation(employee_id, turn["conversation_id"])
            agent = agents_by_id.get(conv["skill_id"]) if conv else None
            if agent is not None and hasattr(agent, "cancel_run"):
                try:
                    agent.cancel_run(turn_id)
                except Exception:
                    logger.debug("agent.cancel_run ignored for %s", turn_id)
            if active.task is not None:
                active.task.cancel()
        else:
            cancelled = store.update_turn(turn_id, status="cancelled")
            if cancelled is not None:
                _emit(turn_id, "terminal", {"turn": cancelled})
                return JSONResponse(cancelled, status_code=200)
        return JSONResponse(updated or turn, status_code=202)

    @app.post("/v1/turns/{turn_id}/inputs")
    async def answer_turn_input(turn_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        turn = store.get_turn(employee_id, turn_id)
        if turn is None:
            return _error_response(404, "not_found", "Turn not found")
        return _error_response(409, "conflict", "Turn is not awaiting input")

    @app.post("/v1/uploads")
    async def upload_attachment(request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        try:
            body = await request.json()
        except Exception:
            return _error_response(422, "invalid_input", "Invalid JSON payload")
        if not isinstance(body, dict):
            return _error_response(422, "invalid_input", "Invalid JSON payload")

        skill_id = str(body.get("skill_id") or "").strip()
        filename = str(body.get("filename") or "").strip()
        mime_type = str(body.get("mime_type") or "application/octet-stream")
        content_b64 = body.get("content_base64")
        skill_spec = skills_by_id.get(skill_id)
        if skill_spec is None:
            return _error_response(404, "not_found", "Skill not found")
        rule = skill_spec.get("attachments")
        if not rule or not filename or not isinstance(content_b64, str):
            return _error_response(422, "invalid_input", "Attachment rejected by skill rules")
        try:
            raw_bytes = base64.b64decode(content_b64, validate=True)
        except Exception:
            return _error_response(422, "invalid_input", "Invalid base64 payload")
        max_bytes = min(int(rule.get("max_bytes", 0)), MAX_UPLOAD_BYTES)
        if len(raw_bytes) > max_bytes:
            return _error_response(422, "invalid_input", "Attachment exceeds max_bytes")
        meta = store.save_artifact(
            employee_id=employee_id,
            filename=filename,
            mime_type=mime_type,
            raw_bytes=raw_bytes,
            egress=skill_spec["egress"],
        )
        return JSONResponse({"artifact": meta}, status_code=201)

    @app.get("/v1/artifacts/{artifact_id}/download")
    async def download_artifact(artifact_id: str, request: Request) -> Response:
        denied = _check_auth(request)
        if denied is not None:
            return denied
        found = store.get_artifact(employee_id, artifact_id)
        if found is None:
            return _error_response(404, "not_found", "Artifact not found")
        meta, mime_type, storage_path = found
        if not storage_path.is_file():
            return _error_response(404, "not_found", "Artifact file missing")
        raw_bytes = storage_path.read_bytes()
        return Response(
            content=raw_bytes,
            status_code=200,
            media_type=mime_type,
            headers={
                "Content-Length": str(len(raw_bytes)),
                "Content-Disposition": f'attachment; filename="{quote(meta["filename"])}"',
            },
        )

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def catch_all_not_found(full_path: str) -> Response:
        return _error_response(404, "not_found", "Not found")

    return app
