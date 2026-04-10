"""Business strategy domain specialist."""
from citnega.packages.agents.domain._domain_base import DomainAgent


class BusinessAgent(DomainAgent):
    agent_id    = "business"
    name        = "business_agent"
    description = "Business strategy: market analysis, operations, product, go-to-market."
