"""Domain specialist agents."""

from citnega.packages.agents.domain.software_engineering import SoftwareEngAgent
from citnega.packages.agents.domain.finance    import FinanceAgent
from citnega.packages.agents.domain.legal      import LegalAgent
from citnega.packages.agents.domain.healthcare import HealthcareAgent
from citnega.packages.agents.domain.business   import BusinessAgent
from citnega.packages.agents.domain.trader     import TraderAgent
from citnega.packages.agents.domain.control_systems import ControlSystemsAgent

ALL_DOMAIN_AGENTS = [
    SoftwareEngAgent, FinanceAgent, LegalAgent, HealthcareAgent,
    BusinessAgent, TraderAgent, ControlSystemsAgent,
]

__all__ = [
    "SoftwareEngAgent", "FinanceAgent", "LegalAgent", "HealthcareAgent",
    "BusinessAgent", "TraderAgent", "ControlSystemsAgent",
    "ALL_DOMAIN_AGENTS",
]
