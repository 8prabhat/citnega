"""Finance domain specialist."""

from citnega.packages.agents.domain._domain_base import DomainAgent


class FinanceAgent(DomainAgent):
    agent_id = "finance"
    name = "finance_agent"
    description = "Financial analyst: equity research, risk, portfolio, macroeconomics."
