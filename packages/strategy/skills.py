from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import yaml  # type: ignore[import-untyped]

from citnega.packages.strategy.models import SkillDescriptor


class SkillFrontMatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    supported_modes: list[str] = Field(
        default_factory=lambda: ["chat", "plan", "explore", "research", "code", "review", "operate"]
    )
    tags: list[str] = Field(default_factory=list)


def _split_front_matter(text: str) -> tuple[dict[str, Any], str, bool]:
    stripped = text.lstrip()
    if not stripped.startswith("---\n"):
        return {}, text, False
    _, _, rest = stripped.partition("---\n")
    front_matter, sep, body = rest.partition("\n---\n")
    if not sep:
        return {}, text, False
    data = yaml.safe_load(front_matter) or {}
    return data, body.strip(), True


def load_skill(skill_file: Path) -> SkillDescriptor:
    content = skill_file.read_text(encoding="utf-8")
    raw_front_matter, body, has_front_matter = _split_front_matter(content)
    if not has_front_matter:
        raise ValueError(f"{skill_file} must include YAML front matter delimited by --- blocks.")

    front_matter = SkillFrontMatter.model_validate(raw_front_matter)
    name = (front_matter.name or skill_file.parent.name).strip()
    description = front_matter.description.strip()
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
        triggers=[item.strip() for item in front_matter.triggers if item.strip()],
        preferred_tools=[item.strip() for item in front_matter.preferred_tools if item.strip()],
        preferred_agents=[item.strip() for item in front_matter.preferred_agents if item.strip()],
        supported_modes=[item.strip() for item in front_matter.supported_modes if item.strip()] or ["chat", "plan", "explore", "research", "code", "review", "operate"],
        tags=[item.strip() for item in front_matter.tags if item.strip()],
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
