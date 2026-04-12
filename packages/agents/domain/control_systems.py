"""Control Systems domain specialist."""

from citnega.packages.agents.domain._domain_base import DomainAgent


class ControlSystemsAgent(DomainAgent):
    agent_id = "control_systems"
    name = "control_systems_agent"
    description = "Control & automation: PID, state-space, embedded systems, SCADA."
