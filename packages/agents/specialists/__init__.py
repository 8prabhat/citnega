"""Specialist agents."""

from citnega.packages.agents.specialists.auto_research_agent import AutoResearchAgent
from citnega.packages.agents.specialists.customer_support_agent import CustomerSupportAgent
from citnega.packages.agents.specialists.devops_agent import DevOpsAgent
from citnega.packages.agents.specialists.hr_agent import HRAgent
from citnega.packages.agents.specialists.marketing_agent import MarketingAgent
from citnega.packages.agents.specialists.product_manager_agent import ProductManagerAgent
from citnega.packages.agents.specialists.qa_engineer_agent import QAEngineerAgent
from citnega.packages.agents.specialists.sales_agent import SalesAgent
from citnega.packages.agents.specialists.ux_design_agent import UXDesignAgent
from citnega.packages.agents.specialists.business_analyst_agent import BusinessAnalystAgent
from citnega.packages.agents.specialists.code_agent import CodeAgent
from citnega.packages.agents.specialists.data_agent import DataAgent
from citnega.packages.agents.specialists.data_analyst_agent import DataAnalystAgent
from citnega.packages.agents.specialists.data_scientist_agent import DataScientistAgent
from citnega.packages.agents.specialists.file_agent import FileAgent
from citnega.packages.agents.specialists.financial_controller_agent import FinancialControllerAgent
from citnega.packages.agents.specialists.lawyer_agent import LawyerAgent
from citnega.packages.agents.specialists.ml_engineer_agent import MLEngineerAgent
from citnega.packages.agents.specialists.qa_agent import QAAgent
from citnega.packages.agents.specialists.release_agent import ReleaseAgent
from citnega.packages.agents.specialists.research_agent import ResearchAgent
from citnega.packages.agents.specialists.risk_manager_agent import RiskManagerAgent
from citnega.packages.agents.specialists.security_agent import SecurityAgent
from citnega.packages.agents.specialists.sre_agent import SREAgent
from citnega.packages.agents.specialists.summary_agent import SummaryAgent
from citnega.packages.agents.specialists.writing_agent import WritingAgent

ALL_SPECIALISTS = [
    # Research specialists
    AutoResearchAgent,
    # Original specialists
    ResearchAgent,
    SummaryAgent,
    FileAgent,
    DataAgent,
    WritingAgent,
    CodeAgent,
    QAAgent,
    SecurityAgent,
    ReleaseAgent,
    # Domain specialists — Batch D
    BusinessAnalystAgent,
    DataAnalystAgent,
    DataScientistAgent,
    SREAgent,
    MLEngineerAgent,
    RiskManagerAgent,
    FinancialControllerAgent,
    LawyerAgent,
    # Role-coverage specialists — Batch 4
    HRAgent,
    ProductManagerAgent,
    MarketingAgent,
    SalesAgent,
    UXDesignAgent,
    CustomerSupportAgent,
    DevOpsAgent,
    QAEngineerAgent,
]

__all__ = [
    "ALL_SPECIALISTS",
    "AutoResearchAgent",
    "BusinessAnalystAgent",
    "CodeAgent",
    "CustomerSupportAgent",
    "DataAgent",
    "DataAnalystAgent",
    "DataScientistAgent",
    "DevOpsAgent",
    "FileAgent",
    "FinancialControllerAgent",
    "HRAgent",
    "LawyerAgent",
    "MarketingAgent",
    "MLEngineerAgent",
    "ProductManagerAgent",
    "QAAgent",
    "QAEngineerAgent",
    "ReleaseAgent",
    "ResearchAgent",
    "RiskManagerAgent",
    "SalesAgent",
    "SecurityAgent",
    "SREAgent",
    "SummaryAgent",
    "UXDesignAgent",
    "WritingAgent",
]
