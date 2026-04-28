"""
Unit tests for Batch 2 new skill domains.

Covers:
- All 7 new domain skill modules are present and non-empty
- Every skill has the 8 required keys
- No duplicate skill names in BUILTIN_SKILL_INDEX
- Per-domain trigger non-empty checks
"""

from __future__ import annotations

import pytest


def test_all_new_skill_domains_present():
    from citnega.packages.skills._hr import HR_SKILLS
    from citnega.packages.skills._product import PRODUCT_SKILLS
    from citnega.packages.skills._marketing import MARKETING_SKILLS
    from citnega.packages.skills._sales import SALES_SKILLS
    from citnega.packages.skills._ux import UX_SKILLS
    from citnega.packages.skills._support import SUPPORT_SKILLS
    from citnega.packages.skills._finance_advanced import FINANCE_ADVANCED_SKILLS

    assert len(HR_SKILLS) >= 4
    assert len(PRODUCT_SKILLS) >= 4
    assert len(MARKETING_SKILLS) >= 4
    assert len(SALES_SKILLS) >= 4
    assert len(UX_SKILLS) >= 3
    assert len(SUPPORT_SKILLS) >= 3
    assert len(FINANCE_ADVANCED_SKILLS) >= 3


def test_all_new_skill_domains_in_builtin_skill_index():
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills._hr import HR_SKILLS
    from citnega.packages.skills._product import PRODUCT_SKILLS
    from citnega.packages.skills._marketing import MARKETING_SKILLS
    from citnega.packages.skills._sales import SALES_SKILLS
    from citnega.packages.skills._ux import UX_SKILLS
    from citnega.packages.skills._support import SUPPORT_SKILLS
    from citnega.packages.skills._finance_advanced import FINANCE_ADVANCED_SKILLS

    all_new = (
        HR_SKILLS + PRODUCT_SKILLS + MARKETING_SKILLS + SALES_SKILLS
        + UX_SKILLS + SUPPORT_SKILLS + FINANCE_ADVANCED_SKILLS
    )
    for skill in all_new:
        assert skill["name"] in BUILTIN_SKILL_INDEX, f"Skill '{skill['name']}' missing from index"


_REQUIRED_KEYS = {"name", "description", "triggers", "preferred_tools",
                   "preferred_agents", "supported_modes", "tags", "body"}


def test_every_skill_has_required_fields():
    from citnega.packages.skills.builtins import BUILTIN_SKILLS
    for skill in BUILTIN_SKILLS:
        missing = _REQUIRED_KEYS - set(skill.keys())
        assert not missing, f"Skill '{skill.get('name')}' missing keys: {missing}"


def test_no_duplicate_skill_names():
    from citnega.packages.skills.builtins import BUILTIN_SKILLS, BUILTIN_SKILL_INDEX
    assert len(BUILTIN_SKILLS) == len(BUILTIN_SKILL_INDEX), (
        f"Duplicate skill names detected: {len(BUILTIN_SKILLS)} skills but {len(BUILTIN_SKILL_INDEX)} unique"
    )


def test_hr_skills_triggers_non_empty():
    from citnega.packages.skills._hr import HR_SKILLS
    for skill in HR_SKILLS:
        assert skill["triggers"], f"HR skill '{skill['name']}' has empty triggers"


def test_product_skills_triggers_non_empty():
    from citnega.packages.skills._product import PRODUCT_SKILLS
    for skill in PRODUCT_SKILLS:
        assert skill["triggers"], f"Product skill '{skill['name']}' has empty triggers"


def test_marketing_skills_triggers_non_empty():
    from citnega.packages.skills._marketing import MARKETING_SKILLS
    for skill in MARKETING_SKILLS:
        assert skill["triggers"], f"Marketing skill '{skill['name']}' has empty triggers"


def test_sales_skills_triggers_non_empty():
    from citnega.packages.skills._sales import SALES_SKILLS
    for skill in SALES_SKILLS:
        assert skill["triggers"], f"Sales skill '{skill['name']}' has empty triggers"


def test_ux_skills_triggers_non_empty():
    from citnega.packages.skills._ux import UX_SKILLS
    for skill in UX_SKILLS:
        assert skill["triggers"], f"UX skill '{skill['name']}' has empty triggers"


def test_support_skills_triggers_non_empty():
    from citnega.packages.skills._support import SUPPORT_SKILLS
    for skill in SUPPORT_SKILLS:
        assert skill["triggers"], f"Support skill '{skill['name']}' has empty triggers"


def test_finance_advanced_skills_triggers_non_empty():
    from citnega.packages.skills._finance_advanced import FINANCE_ADVANCED_SKILLS
    for skill in FINANCE_ADVANCED_SKILLS:
        assert skill["triggers"], f"Finance advanced skill '{skill['name']}' has empty triggers"
