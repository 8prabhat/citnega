"""
Built-in skills shipped with citnega.

Skills are split into domain modules for maintainability. This module is the
single public surface — all consumers import BUILTIN_SKILLS and BUILTIN_SKILL_INDEX
from here; the domain split is an internal implementation detail.

Skills in the user's workfolder/skills/ directory override builtins by name
(WorkspaceCapabilityProvider uses overwrite=True).
"""

from __future__ import annotations

from citnega.packages.skills._auto_research import AUTO_RESEARCH_SKILLS
from citnega.packages.skills._business import BUSINESS_SKILLS
from citnega.packages.skills._core import CORE_SKILLS
from citnega.packages.skills._data_ml import DATA_ML_SKILLS
from citnega.packages.skills._finance_advanced import FINANCE_ADVANCED_SKILLS
from citnega.packages.skills._hr import HR_SKILLS
from citnega.packages.skills._marketing import MARKETING_SKILLS
from citnega.packages.skills._ops import OPS_SKILLS
from citnega.packages.skills._product import PRODUCT_SKILLS
from citnega.packages.skills._risk_legal import RISK_LEGAL_SKILLS
from citnega.packages.skills._sales import SALES_SKILLS
from citnega.packages.skills._support import SUPPORT_SKILLS
from citnega.packages.skills._ux import UX_SKILLS

BUILTIN_SKILLS: list[dict] = [
    *CORE_SKILLS,
    *AUTO_RESEARCH_SKILLS,
    *BUSINESS_SKILLS,
    *DATA_ML_SKILLS,
    *OPS_SKILLS,
    *RISK_LEGAL_SKILLS,
    *HR_SKILLS,
    *PRODUCT_SKILLS,
    *MARKETING_SKILLS,
    *SALES_SKILLS,
    *UX_SKILLS,
    *SUPPORT_SKILLS,
    *FINANCE_ADVANCED_SKILLS,
]

# Index by name for O(1) lookup
BUILTIN_SKILL_INDEX: dict[str, dict] = {s["name"]: s for s in BUILTIN_SKILLS}
