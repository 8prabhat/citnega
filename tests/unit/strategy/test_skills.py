from __future__ import annotations

import pytest

from citnega.packages.strategy.skills import load_skill, load_skills


def test_load_skill_front_matter(tmp_path):
    skill_dir = tmp_path / "skills" / "release"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: release-readiness
description: Release workflow guidance
triggers: [release, deploy]
preferred_tools: [quality_gate]
preferred_agents: [qa_agent]
supported_modes: [plan, review]
tags: [release]
---
Use the release checklist.
""",
        encoding="utf-8",
    )

    descriptor = load_skill(skill_file)

    assert descriptor.name == "release-readiness"
    assert descriptor.description == "Release workflow guidance"
    assert descriptor.triggers == ["release", "deploy"]
    assert descriptor.preferred_tools == ["quality_gate"]
    assert descriptor.preferred_agents == ["qa_agent"]
    assert descriptor.supported_modes == ["plan", "review"]
    assert descriptor.tags == ["release"]
    assert "release checklist" in descriptor.body


def test_load_skill_requires_front_matter(tmp_path):
    skill_dir = tmp_path / "skills" / "triage"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("First non-empty line becomes the description.\n\nMore detail.", encoding="utf-8")

    with pytest.raises(ValueError, match="must include YAML front matter"):
        load_skill(skill_file)


def test_load_skill_rejects_unknown_front_matter_fields(tmp_path):
    skill_dir = tmp_path / "skills" / "triage"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: triage
unexpected_field: true
---
Body text.
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unexpected_field"):
        load_skill(skill_file)


def test_load_skills_scans_skill_directories(tmp_path):
    root = tmp_path / "skills"
    (root / "one").mkdir(parents=True)
    (root / "two").mkdir(parents=True)
    (root / "one" / "SKILL.md").write_text("---\nname: one\n---\nBody", encoding="utf-8")
    (root / "two" / "SKILL.md").write_text("---\nname: two\n---\nBody", encoding="utf-8")

    loaded = load_skills(root)

    assert sorted(loaded) == ["one", "two"]


# ── SkillActivatedEvent emission ──────────────────────────────────────────────


def test_set_session_skills_emits_skill_activated_event():
    """set_session_skills() must emit SkillActivatedEvent for each skill."""
    from unittest.mock import MagicMock

    from citnega.packages.protocol.events.planning import SkillActivatedEvent
    from citnega.packages.runtime.app_service import ApplicationService
    from citnega.packages.shared.registry import CallableRegistry

    events: list = []
    emitter = MagicMock()
    emitter.emit.side_effect = events.append

    runtime = MagicMock()
    runtime.get_runner = MagicMock(return_value=None)
    runtime.capability_registry = None

    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = runtime
    svc._emitter = emitter
    svc._callable_registry = CallableRegistry()
    svc._capability_registry_cache = None
    svc._app_home = None

    svc.set_session_skills("sess-1", ["release", "security"])

    skill_events = [e for e in events if isinstance(e, SkillActivatedEvent)]
    assert len(skill_events) == 2
    skill_names = {e.skill_name for e in skill_events}
    assert skill_names == {"release", "security"}
    for e in skill_events:
        assert e.session_id == "sess-1"
