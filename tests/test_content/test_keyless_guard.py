"""KR-3 invariants: zero third-party key imports; SSRF guard applied.

The keyless absolute (the brief's standing rule) forbids *importing or calling* a keyed
provider SDK / reading an API-key env var. Verbatim doc references to "Firecrawl"
(the algorithm we ported, $0) and the mandated `FIRECRAWL_CLEAN_PROMPT` constant name
are allowed — the contract requires that export. This guard therefore parses the AST
and inspects only `import`/`from … import` statements + name loads, never docstrings or
comments, so it catches a real keyed dependency without false-positiving on prose.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bad_research" / "web" / "content"

# substrings that, if they appear in an import target module path, mean a keyed SDK
BANNED_IMPORT_SUBSTRINGS = (
    "cohere", "tavily", "exa_py", "firecrawl", "browserbase",
    "agentql", "browser_use", "openai", "stagehand", "jina",
)


def _imported_modules(tree: ast.AST) -> list[str]:
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


def test_no_keyed_provider_imports() -> None:
    for py in SRC.glob("*.py"):
        tree = ast.parse(py.read_text())
        for mod in _imported_modules(tree):
            low = mod.lower()
            for token in BANNED_IMPORT_SUBSTRINGS:
                assert token not in low, f"{py.name} imports {mod!r} — not keyless"


def _is_env_read(node: ast.AST) -> bool:
    """True if the node is os.getenv(...) / os.environ.get(...) / os.environ[...]."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ("getenv", "get"):
            return True
    if isinstance(node, ast.Subscript):
        v = node.value
        if isinstance(v, ast.Attribute) and v.attr == "environ":
            return True
    return False


def test_no_api_key_env_reads() -> None:
    # the package must never READ a keyed-provider API key from the env (keyless path).
    # docstring/comment mentions of ANTHROPIC_API_KEY are allowed; an env read is not.
    for py in SRC.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not _is_env_read(node):
                continue
            literals = [
                n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            for lit in literals:
                assert "API_KEY" not in lit.upper(), (
                    f"{py.name} reads {lit!r} from the environment — not keyless"
                )


def test_fetch_clean_applies_ssrf_guard() -> None:
    text = (SRC / "fetch_clean.py").read_text()
    assert "assert_url_safe" in text
    assert "safe_redirect_get" in text   # static rung uses the manual-redirect re-check
