"""Trader domain specialist."""
from citnega.packages.agents.domain._domain_base import DomainAgent


class TraderAgent(DomainAgent):
    agent_id    = "trader"
    name        = "trader_agent"
    description = "Quantitative trading: strategies, risk management, technical analysis."
