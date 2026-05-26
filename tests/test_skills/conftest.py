from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "src" / "bad_research" / "skills"


@pytest.fixture
def skills_dir() -> Path:
    return SKILLS_DIR


@pytest.fixture
def known_skills(skills_dir: Path) -> set[str]:
    return {p.stem for p in skills_dir.glob("bad-research*.md")} | {"bad-research"}
