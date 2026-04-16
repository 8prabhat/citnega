from __future__ import annotations

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


def test_load_skill_falls_back_to_body_text(tmp_path):
    skill_dir = tmp_path / "skills" / "triage"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("First non-empty line becomes the description.\n\nMore detail.", encoding="utf-8")

    descriptor = load_skill(skill_file)

    assert descriptor.name == "triage"
    assert descriptor.description == "First non-empty line becomes the description."


def test_load_skills_scans_skill_directories(tmp_path):
    root = tmp_path / "skills"
    (root / "one").mkdir(parents=True)
    (root / "two").mkdir(parents=True)
    (root / "one" / "SKILL.md").write_text("---\nname: one\n---\nBody", encoding="utf-8")
    (root / "two" / "SKILL.md").write_text("---\nname: two\n---\nBody", encoding="utf-8")

    loaded = load_skills(root)

    assert sorted(loaded) == ["one", "two"]
