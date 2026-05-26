"""Structural validator for Bad Research skill prompts.

A skill .md is valid iff:
  - it has YAML frontmatter delimited by `---` with `name` and `description`
  - `name` matches the filename slug (sans .md)
  - it contains every required section header for its kind (entry vs step)
  - every `Skill(skill: "X")` / `bad-research-N-...` reference resolves to a
    skill that exists in the same skills dir (or is the entry skill)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ENTRY_REQUIRED = ["## Tier routing", "## Bootstrap", "## Recovery"]
STEP_REQUIRED = ["**Tier gate:**", "**Goal:**", "## Recover state", "## Exit criterion"]


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        raise ValueError("no frontmatter block")
    fm = yaml.safe_load(m.group(1))
    if not isinstance(fm, dict) or "name" not in fm or "description" not in fm:
        raise ValueError("frontmatter missing name/description")
    return fm


def referenced_skills(text: str) -> set[str]:
    refs = set(re.findall(r'Skill\(skill:\s*"([a-z0-9.\-]+)"\)', text))
    refs |= set(re.findall(r"\b(bad-research-[0-9.]+-[a-z\-]+)\b", text))
    return refs


def validate_skill(path: Path, known_skills: set[str]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    slug = path.stem if path.name != "SKILL.md" else path.parent.name
    try:
        fm = parse_frontmatter(text)
    except ValueError as e:
        return [f"{path.name}: {e}"]
    if fm["name"] != slug:
        errors.append(f"{path.name}: name '{fm['name']}' != slug '{slug}'")
    required = ENTRY_REQUIRED if fm["name"] in ("bad-research", "hyperresearch") else STEP_REQUIRED
    for section in required:
        if section not in text:
            errors.append(f"{path.name}: missing required section '{section}'")
    for ref in referenced_skills(text):
        if ref not in known_skills and ref != "bad-research":
            errors.append(f"{path.name}: unresolved skill reference '{ref}'")
    return errors
