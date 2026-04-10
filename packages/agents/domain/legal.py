"""Legal domain specialist."""
from citnega.packages.agents.domain._domain_base import DomainAgent


class LegalAgent(DomainAgent):
    agent_id    = "legal"
    name        = "legal_agent"
    description = "Legal research: contracts, corporate law, IP, regulatory compliance."
