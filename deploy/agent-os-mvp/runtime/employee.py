"""Authenticated employee gateway exposing only /v1 cloud-session routes and /health.

Internal AgentOS endpoints (/agents, /sessions, docs, WebSocket) are not exposed
on the employee listener. Skill agents run in-process over shared relay_model
and PostgreSQL session history while /v1 product records persist in SQLite.
"""

from common import CONFIG, DATA
from script_agents import skill_agents
from v1_gateway import create_v1_app

app = create_v1_app(
    agents=skill_agents,
    employee_token=CONFIG["employee_token"],
    data_dir=DATA,
    employee_id="mvp-jax",
    display_name="Jax",
)
