"""Administrative AgentOS, reachable only through the operator's SSH tunnel."""

from agno.db.in_memory import InMemoryDb
from agno.os import AgentOS
from common import db, registry
from script_agents import script_agents

# Keep the administration Registry while preventing the two script Agents from
# inheriting the default PostgreSQL database.
script_db = InMemoryDb()
for agent in script_agents:
    agent.db = script_db

agent_os = AgentOS(
    id="jax-agent-os-poc",
    name="内网 AgentOS MVP",
    agents=script_agents,
    db=db,
    registry=registry,
    auto_provision_dbs=False,
    tracing=False,
    telemetry=False,
)
app = agent_os.get_app()
