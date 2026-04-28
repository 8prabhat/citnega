"""
Integration tests for Batch 8 skill coverage:
- All 45 skills in index
- HR/product/marketing/sales/UX/support/finance trigger matching
- No duplicates
- Every skill has all required fields
"""

from __future__ import annotations

import pytest

from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX, BUILTIN_SKILLS
from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher


# ── Coverage count ─────────────────────────────────────────────────────────────

def test_all_new_skill_domains_present_in_index():
    expected_domains = {
        # HR domain
        "recruitment_pipeline", "performance_review", "org_design", "onboarding_plan",
        # Product domain
        "product_spec", "roadmap_planning", "user_research", "competitive_analysis",
        # Marketing domain
        "campaign_brief", "content_calendar", "seo_audit", "brand_guidelines",
        # Sales domain
        "deal_review", "proposal_writing", "pipeline_analysis", "account_plan",
        # UX domain
        "design_critique", "wireframe_spec", "usability_testing",
        # Support domain
        "ticket_triage", "knowledge_article", "feedback_synthesis",
        # Finance advanced domain
        "financial_model", "budget_planning", "investor_reporting",
    }
    missing = expected_domains - set(BUILTIN_SKILL_INDEX.keys())
    assert not missing, f"Missing skills from index: {missing}"


def test_skill_count_at_least_forty_five():
    assert len(BUILTIN_SKILL_INDEX) >= 45, (
        f"Expected at least 45 skills, found {len(BUILTIN_SKILL_INDEX)}"
    )


def test_no_duplicate_skill_names():
    names = [s["name"] for s in BUILTIN_SKILLS]
    assert len(names) == len(set(names)), "Duplicate skill names detected"


def test_no_duplicate_skill_index_keys():
    assert len(BUILTIN_SKILLS) == len(BUILTIN_SKILL_INDEX), (
        "BUILTIN_SKILLS count does not match BUILTIN_SKILL_INDEX count — possible duplicates"
    )


# ── Required fields ────────────────────────────────────────────────────────────

def test_every_skill_has_required_fields():
    required = {"name", "description", "triggers", "preferred_tools",
                "preferred_agents", "supported_modes", "tags", "body"}
    for skill in BUILTIN_SKILLS:
        missing = required - skill.keys()
        assert not missing, f"Skill {skill.get('name')!r} missing fields: {missing}"


def test_every_skill_has_non_empty_triggers():
    for skill in BUILTIN_SKILLS:
        assert skill.get("triggers"), f"Skill {skill['name']!r} has empty triggers"


def test_every_skill_has_non_empty_body():
    for skill in BUILTIN_SKILLS:
        assert skill.get("body", "").strip(), f"Skill {skill['name']!r} has empty body"


# ── Trigger matching: HR ───────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("I need to write a job description and hire a software engineer", "recruitment_pipeline"),
    ("Let's do a performance review for Q4 using OKR framework", "performance_review"),
    ("Design a new org chart for the engineering department", "org_design"),
    ("Create a first week plan and onboarding schedule for new hire", "onboarding_plan"),
])
def test_hr_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: Product ──────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Write a PRD with product requirements and user stories", "product_spec"),
    ("Build the quarterly roadmap using RICE prioritisation", "roadmap_planning"),
    ("Run user interviews and synthesise customer insight", "user_research"),
    ("Do a competitive analysis and market landscape review", "competitive_analysis"),
])
def test_product_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: Marketing ────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Create a go-to-market campaign brief for our product launch", "campaign_brief"),
    ("Build an editorial content calendar for the next quarter", "content_calendar"),
    ("Run an SEO audit and check our meta tags and keywords", "seo_audit"),
    ("Define brand guidelines and tone of voice for the company", "brand_guidelines"),
])
def test_marketing_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: Sales ────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Do a MEDDIC deal review for this opportunity", "deal_review"),
    ("Write a sales proposal and statement of work for the client", "proposal_writing"),
    ("Analyse the pipeline and generate a sales forecast", "pipeline_analysis"),
    ("Create an account plan for our key strategic accounts", "account_plan"),
])
def test_sales_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: UX ───────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Please do a UX critique and heuristic evaluation of this design", "design_critique"),
    ("Create a wireframe spec with screen flow and information architecture", "wireframe_spec"),
    ("Plan a usability test with think-aloud protocol", "usability_testing"),
])
def test_ux_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: Support ──────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Triage this P1 support ticket and customer issue", "ticket_triage"),
    ("Write a knowledge base article and FAQ for this problem", "knowledge_article"),
    ("Synthesise NPS and CSAT customer feedback data", "feedback_synthesis"),
])
def test_support_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )


# ── Trigger matching: Finance advanced ────────────────────────────────────────

@pytest.mark.parametrize("phrase,expected_skill", [
    ("Build a DCF valuation model and three-statement financial model", "financial_model"),
    ("Create an annual zero-based budget planning template", "budget_planning"),
    ("Prepare an investor report and board pack with KPI dashboard", "investor_reporting"),
])
def test_finance_triggers_activate_correct_skill(phrase, expected_skill):
    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match(phrase)
    assert expected_skill in matched, (
        f"Expected {expected_skill!r} for phrase {phrase!r}, got {matched}"
    )
