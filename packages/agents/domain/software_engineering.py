"""Software Engineering domain specialist."""
from citnega.packages.agents.domain._domain_base import DomainAgent


class SoftwareEngAgent(DomainAgent):
    agent_id    = "software_engineering"
    name        = "software_engineering_agent"
    description = "Senior software engineer: design, code review, debugging, architecture."
