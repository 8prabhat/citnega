"""Integration tests: skill trigger matching and impact scoring."""
from __future__ import annotations

import pytest


def test_trigger_matcher_activates_skill_on_debug_input() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher

    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match("help me debug this error in my Python script")
    assert "debug_session" in matched


def test_trigger_matcher_activates_code_review_on_review_input() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher

    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match("please do a code review of this pull request")
    assert len(matched) > 0


def test_trigger_matcher_respects_limit() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher

    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match("review code and debug errors and research vulnerabilities", limit=2)
    assert len(matched) <= 2


def test_trigger_matcher_no_match_returns_empty() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher

    matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)
    matched = matcher.match("what is the weather today")
    assert isinstance(matched, list)


def test_skill_impact_analyzer_scores_matching_reply() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.impact_analyzer import SkillImpactAnalyzer

    analyzer = SkillImpactAnalyzer()
    skill = BUILTIN_SKILL_INDEX.get("debug_session")
    assert skill is not None, "debug_session skill must exist"
    triggers = skill.get("triggers", [])
    reply = " ".join(triggers[:3]) + " traceback error root cause"
    scores = analyzer.analyze(["debug_session"], reply, [], skill_index=BUILTIN_SKILL_INDEX)
    assert len(scores) > 0
    assert scores[0].score > 0.1


def test_skill_impact_analyzer_zero_score_irrelevant_reply() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
    from citnega.packages.skills.impact_analyzer import SkillImpactAnalyzer

    analyzer = SkillImpactAnalyzer()
    scores = analyzer.analyze(["debug_session"], "the weather is sunny today", [], skill_index=BUILTIN_SKILL_INDEX)
    assert scores == []


def test_all_builtin_skills_have_required_fields() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILLS

    for skill in BUILTIN_SKILLS:
        assert "name" in skill, f"skill missing 'name': {skill}"
        assert "description" in skill, f"skill {skill.get('name')} missing 'description'"
        assert "triggers" in skill, f"skill {skill.get('name')} missing 'triggers'"
        assert len(skill["triggers"]) > 0, f"skill {skill.get('name')} has empty triggers"


def test_builtin_skill_index_matches_skills_list() -> None:
    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX, BUILTIN_SKILLS

    assert len(BUILTIN_SKILL_INDEX) == len(BUILTIN_SKILLS)
    for skill in BUILTIN_SKILLS:
        assert skill["name"] in BUILTIN_SKILL_INDEX
