"""C-2 follow-up guard: no LIVE 'read this file' instruction may point at the
artifacts that C-2 renamed away.

C-2 merged step 7 (`source-tensions`) into step 6 (`cross-locus-reconcile`) and
renamed the output artifacts `research/comparisons.md` + `research/temp/source-tensions.json`
into a single `research/temp/tensions.md`. The rename was incomplete: several
spawned-agent prompts in `hooks.py` and the step-11 recover-state / synthesizer
spawn args still told agents to *read* the now-nonexistent old files. Those are
runtime breaks — an agent would `Read` a path that no longer exists.

This guard scans:
  1. The step-skill files' input / recover-state declarations.
  2. The embedded `*_AGENT` prompt constants in `hooks.py`.

It asserts no READ instruction or input-path declaration names `comparisons.md`
or `source-tensions.json`. It deliberately tolerates the legitimate survivors:
hygiene/polish prompts that STRIP those literal strings, "was/replaces"
provenance annotations, and forward-reference narration that merely mentions the
old name. We detect a READ break by the presence of a literal artifact-path
token (`comparisons.md` / `source-tensions.json`) on a line whose intent is to
*read* / declare an *input path*, not to strip or annotate it.

`evidence-digest.md` is still written and read — it is explicitly out of scope.
"""

from __future__ import annotations

import re
from pathlib import Path

import bad_research.core.hooks as hooks

DEAD_ARTIFACTS = ("comparisons.md", "source-tensions.json")

# Lines whose intent is provenance/stripping/narration, not a live read. A line
# matching one of these markers may legitimately name a dead artifact.
_ALLOWED_MARKERS = (
    "was `comparisons.md`",
    "was comparisons.md",
    "replaces the former",
    "former `comparisons.md`",
    "former comparisons.md",
    "former `source-tensions.json`",
    "former source-tensions.json",
    "strip",          # hygiene prompts that strip the literal token from prose
    "no pipeline vocabulary",
    "pipeline vocabulary",
)

# Tokens that signal a READ / INPUT-PATH declaration on the same line.
_READ_MARKERS = (
    "read ",
    "re-read ",
    "_path:",
    "_path**:",
    "**read",
)


def _line_is_dead_read(line: str) -> bool:
    low = line.lower()
    if not any(a in low for a in DEAD_ARTIFACTS):
        return False
    if any(m in low for m in _ALLOWED_MARKERS):
        return False
    return any(m in low for m in _READ_MARKERS)


def _agent_prompt_constants() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in dir(hooks):
        if name.endswith("_AGENT"):
            val = getattr(hooks, name)
            if isinstance(val, str):
                out[name] = val
    return out


def test_no_step_skill_declares_a_dead_artifact_as_an_input(skills_dir: Path):
    """The step-skill recover-state / input sections must not declare a read of
    `comparisons.md` or `source-tensions.json` — they were merged into tensions.md."""
    offenders: list[str] = []
    for p in sorted(skills_dir.glob("bad-research*.md")):
        for n, line in enumerate(p.read_text().splitlines(), start=1):
            if _line_is_dead_read(line):
                offenders.append(f"{p.name}:{n}: {line.strip()}")
    assert not offenders, "dead-artifact READ in step skills:\n" + "\n".join(offenders)


def test_no_agent_prompt_in_hooks_reads_a_dead_artifact():
    """Embedded `*_AGENT` prompt constants in hooks.py must not instruct an agent
    to read `comparisons.md` or `source-tensions.json` (merged into tensions.md)."""
    offenders: list[str] = []
    for name, body in _agent_prompt_constants().items():
        for n, line in enumerate(body.splitlines(), start=1):
            if _line_is_dead_read(line):
                offenders.append(f"hooks.{name} line {n}: {line.strip()}")
    assert not offenders, "dead-artifact READ in *_AGENT prompts:\n" + "\n".join(offenders)


def test_corpus_critic_input_var_is_tensions_path():
    """Step 8 passes `tensions_path: research/temp/tensions.md`; the corpus-critic
    prompt must declare the matching `tensions_path` input, not the old
    `comparisons_path: research/comparisons.md`."""
    body = hooks.CORPUS_CRITIC_AGENT
    assert "tensions_path" in body, "corpus critic must take tensions_path"
    assert "research/temp/tensions.md" in body, "corpus critic must point at tensions.md"
    # the old input var + old path must be gone
    assert not re.search(r"comparisons_path.*comparisons\.md", body), \
        "stale comparisons_path input survives in corpus-critic prompt"
