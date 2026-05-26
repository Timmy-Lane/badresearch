import pytest

from tests.test_skills.validate import parse_frontmatter, referenced_skills


def test_parse_frontmatter_extracts_name():
    fm = parse_frontmatter("---\nname: x\ndescription: y\n---\nbody")
    assert fm["name"] == "x"


def test_parse_frontmatter_rejects_missing():
    with pytest.raises(ValueError):
        parse_frontmatter("no frontmatter here")


def test_referenced_skills_finds_skill_calls():
    text = 'Invoke `Skill(skill: "bad-research-2-width-sweep")`.'
    assert "bad-research-2-width-sweep" in referenced_skills(text)
