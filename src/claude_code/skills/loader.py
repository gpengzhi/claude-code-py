"""Skill loader -- discovers and loads skill markdown files.

Maps to src/skills/loadSkillsDir.ts in the TypeScript codebase.
Skills are Markdown files with YAML frontmatter in .claude/skills/ directories.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SKILL_DIR_NAME = "skills"
SKILL_FILENAME = "SKILL.md"
LEGACY_COMMANDS_DIR = "commands"


def find_skill_dirs(cwd: Path) -> list[Path]:
    """Find all .claude/skills/ directories in the hierarchy.

    Search order (highest to lowest precedence):
    1. <cwd>/.claude/skills/
    2. Walk up to git root, checking each .claude/skills/
    3. ~/.claude/skills/ (user-level)
    """
    dirs: list[Path] = []

    # 1. Walk up from cwd
    current = cwd.resolve()
    home = Path.home().resolve()
    checked: set[str] = set()

    while current != current.parent:
        key = str(current)
        if key in checked:
            break
        checked.add(key)

        skill_dir = current / ".claude" / SKILL_DIR_NAME
        if skill_dir.is_dir():
            dirs.append(skill_dir)

        # Also check legacy commands dir
        cmd_dir = current / ".claude" / LEGACY_COMMANDS_DIR
        if cmd_dir.is_dir() and cmd_dir not in dirs:
            dirs.append(cmd_dir)

        if current == home:
            break
        current = current.parent

    # 2. User-level
    user_skills = home / ".claude" / SKILL_DIR_NAME
    if user_skills.is_dir() and user_skills not in dirs:
        dirs.append(user_skills)

    return dirs


def parse_skill_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from a skill markdown file.

    Returns (frontmatter_dict, body_content).
    """
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, match.group(2).strip()


def load_skill_file(path: Path) -> dict[str, Any] | None:
    """Load a single skill file.

    Skill format: Markdown with YAML frontmatter containing:
    - description: shown in help
    - when_to_use: for model-invoked selection
    - allowed-tools: restricts which tools the skill can use
    - user-invocable: whether user can type /skill-name
    - model: override model
    - effort: effort level
    - context: fork/inline
    - paths: glob patterns for conditional activation
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read skill %s: %s", path, e)
        return None

    frontmatter, body = parse_skill_frontmatter(content)

    # Determine skill name from directory name or file name
    if path.name == SKILL_FILENAME:
        name = path.parent.name
    elif path.suffix == ".md":
        name = path.stem
    else:
        return None

    return {
        "name": name,
        "path": str(path),
        "description": frontmatter.get("description", ""),
        "when_to_use": frontmatter.get("when_to_use", ""),
        "allowed_tools": frontmatter.get("allowed-tools"),
        "user_invocable": frontmatter.get("user-invocable", True),
        "model": frontmatter.get("model"),
        "effort": frontmatter.get("effort"),
        "context": frontmatter.get("context", "inline"),
        "paths": frontmatter.get("paths"),
        "hooks": frontmatter.get("hooks"),
        "body": body,
        "source": "project",
    }


def load_skills_from_dir(skill_dir: Path) -> list[dict[str, Any]]:
    """Load all skills from a directory.

    Supports two formats:
    1. skill-name/SKILL.md (preferred directory format)
    2. skill-name.md (legacy flat file format)
    """
    skills: list[dict[str, Any]] = []

    if not skill_dir.exists():
        return skills

    for item in sorted(skill_dir.iterdir()):
        if item.is_dir():
            # Directory format: skill-name/SKILL.md
            skill_file = item / SKILL_FILENAME
            if skill_file.exists():
                skill = load_skill_file(skill_file)
                if skill:
                    skills.append(skill)
        elif item.suffix == ".md" and item.name != "README.md":
            # Flat file format: skill-name.md
            skill = load_skill_file(item)
            if skill:
                skills.append(skill)

    return skills


def load_all_skills(cwd: Path) -> list[dict[str, Any]]:
    """Load all skills from all skill directories.

    Skills are deduplicated by name (first found wins = highest precedence).
    """
    dirs = find_skill_dirs(cwd)
    seen_names: set[str] = set()
    all_skills: list[dict[str, Any]] = []

    for skill_dir in dirs:
        skills = load_skills_from_dir(skill_dir)
        for skill in skills:
            if skill["name"] not in seen_names:
                seen_names.add(skill["name"])
                all_skills.append(skill)

    return all_skills


def get_user_invocable_skills(cwd: Path) -> list[dict[str, Any]]:
    """Get skills that can be invoked by the user via /skill-name."""
    return [s for s in load_all_skills(cwd) if s.get("user_invocable", True)]
