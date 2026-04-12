"""Healthcare domain specialist."""

from citnega.packages.agents.domain._domain_base import DomainAgent


class HealthcareAgent(DomainAgent):
    agent_id = "healthcare"
    name = "healthcare_agent"
    description = "Medical information: clinical guidelines, pharmacology, diagnostics."
