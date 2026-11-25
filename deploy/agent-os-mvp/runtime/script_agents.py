"""Company skill agents: LLM agents with sandboxed script tools, served by AgentOS.

Each skill is a standard agno Agent (shared relay model + tool functions). The
fixed Python scripts stay the source of deterministic results and keep running
in isolated subprocesses (empty env, no shell, hard timeout).
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Annotated

from agno.agent import Agent
from common import db, model as relay_model
from pydantic import Field

logger = logging.getLogger(__name__)
SKILL_ROOT = Path(__file__).resolve().parent / "private-skills"


def _run_sandbox(skill: str, payload: dict, timeout: float) -> dict:
    """Run one skill script in an isolated subprocess: empty env, no shell, hard timeout."""
    script = SKILL_ROOT / skill / "scripts/run.py"
    if not script.is_file():
        raise ValueError(f"Missing script for {skill}")
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(script)],
            input=json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
            check=False,
            env={},
        )
    except subprocess.TimeoutExpired:
        raise ValueError("脚本执行超时。") from None
    if completed.returncode != 0:
        reason = completed.stderr.strip()
        if not reason or len(reason) > 180 or not reason.isprintable():
            reason = "脚本执行失败。"
        raise ValueError(reason)
    return json.loads(completed.stdout)


def calculate_expression(
    expression: Annotated[
        str,
        Field(description="十进制四则表达式，1–160 个字符，支持括号及正负号，例如 (0.1+0.2)*10"),
    ]
) -> str:
    """计算十进制四则表达式，返回确定性的脚本执行结果。"""
    data = _run_sandbox("calculator", {"expression": expression.strip()}, 3)
    return f"{data['expression']} = {data['result']}"


def query_earthquake_catalog(
    latitude: Annotated[float, Field(description="纬度，-90 至 90，例如 35.68")],
    longitude: Annotated[float, Field(description="经度，-180 至 180，例如 139.69")],
) -> str:
    """查询指定坐标 500 公里内最近 30 天的最新地震记录。"""
    data = _run_sandbox("http-info", {"latitude": latitude, "longitude": longitude}, 12)
    return str(data["answer"])


def _skill_agent(agent_id: str, name: str, description: str, instructions: str, tools) -> Agent:
    return Agent(
        id=agent_id,
        name=name,
        description=description,
        model=relay_model,
        tools=list(tools),
        instructions=instructions,
        db=db,
        telemetry=False,
    )


calculator_agent = _skill_agent(
    "calculator-agent",
    "计算器",
    "十进制四则表达式计算，支持括号及正负号",
    "你是公司「计算器」技能的云端执行 Agent。"
    "用户消息可能包含结构化参数（如：表达式：(0.1+0.2)*10）和自由文本要求。"
    "必须调用 calculate_expression 工具完成计算，禁止心算或改写工具返回的结果。"
    "再根据用户的自由文本要求用中文组织回答；没有补充要求时，简洁给出计算结果。",
    [calculate_expression],
)

earthquake_agent = _skill_agent(
    "http-info-agent",
    "HTTP 查询（地震目录）",
    "查询指定坐标 500 公里内最近 30 天的最新地震记录",
    "你是公司「HTTP 查询（地震目录）」技能的云端执行 Agent。"
    "用户消息可能包含结构化参数（如：纬度：35.68，经度：139.69）和自由文本要求。"
    "必须调用 query_earthquake_catalog 工具查询，结果以工具返回为准。"
    "再根据用户的自由文本要求用中文组织回答；没有补充要求时，简洁给出查询结果。",
    [query_earthquake_catalog],
)

skill_agents = [calculator_agent, earthquake_agent]
