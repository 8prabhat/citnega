from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from citnega.packages.strategy.models import SkillDescriptor


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip()
    if not stripped.startswith("---\n"):
        return {}, text
    _, _, rest = stripped.partition("---\n")
    front_matter, sep, body = rest.partition("\n---\n")
    if not sep:
        return {}, text
    data = yaml.safe_load(front_matter) or {}
    return data, body.strip()


def load_skill(skill_file: Path) -> SkillDescriptor:
    content = skill_file.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(content)
    name = str(front_matter.get("name") or skill_file.parent.name).strip()
    description = str(front_matter.get("description") or "").strip()
    if not description:
        for line in body.splitlines():
            candidate = line.strip()
            if candidate:
                description = candidate[:140]
                break
    return SkillDescriptor(
        name=name,
        description=description or name,
        content_path=str(skill_file),
        triggers=[str(item).strip() for item in front_matter.get("triggers", []) if str(item).strip()],
        preferred_tools=[str(item).strip() for item in front_matter.get("preferred_tools", []) if str(item).strip()],
        preferred_agents=[str(item).strip() for item in front_matter.get("preferred_agents", []) if str(item).strip()],
        supported_modes=[str(item).strip() for item in front_matter.get("supported_modes", []) if str(item).strip()] or ["chat", "plan", "explore", "research", "code", "review", "operate"],
        tags=[str(item).strip() for item in front_matter.get("tags", []) if str(item).strip()],
        body=body,
    )


def load_skills(skills_root: Path) -> dict[str, SkillDescriptor]:
    if not skills_root.exists():
        return {}
    result: dict[str, SkillDescriptor] = {}
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        descriptor = load_skill(skill_file)
        result[descriptor.name] = descriptor
    return result
