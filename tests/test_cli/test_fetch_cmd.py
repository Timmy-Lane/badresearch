"""Tests for the `bad fetch` corpus-bridge command + the funnel keyless-provider
and per-page/per-provider failover fixes (GAP 1 + GAP 2).

`bad fetch` is the URL -> clean -> tagged-vault-note step the fetcher subagent
and skills (steps 2/5/13/16, 11.5) call. These tests mock the content fetch so
no network is touched in CI, then assert: the note is stored + the canonical
envelope shape + the SSRF guard refuses a private/metadata URL + provenance
(`--suggested-by`) lands in frontmatter AND as a vault-graph wiki-link + the
`--tier-max` path routes through the browse ladder.

The funnel tests prove the keyless-correct provider cascade (DdgsProvider leads
so the light-mode `[:1]` slice picks a working lane) and that a provider raising
NotImplementedError (the host WebSearch tool in a subprocess) is skipped rather
than zeroing the run.
"""

import json

import pytest
from typer.testing import CliRunner

from bad_research.cli import app

runner = CliRunner()


# ── helpers ───────────────────────────────────────────────────────────────────

def _init_vault(tmp_path):
    res = runner.invoke(app, ["init", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.stdout
    return tmp_path / "research" / "notes"


def _fake_clean_result(**over):
    """A fetch_clean()-shaped dict (markdown/metadata/published_date/links)."""
    base = {
        "markdown": "# Heading\n\nReal cleaned body text about FastAPI.",
        "metadata": {"title": "FastAPI Docs", "language": "en"},
        "published_date": "2024-01-15",
        "links": [{"href": "https://example.com/a", "text": "a"}],
        "url": "https://fastapi.tiangolo.com/",
    }
    base.update(over)
    return base


# ── bad fetch: store + envelope ─────────────────────────────────────────────────

def test_fetch_stores_note_and_envelope_shape(tmp_path, monkeypatch):
    notes_dir = _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Mock the keyless content pipeline so no network is hit.
    monkeypatch.setattr(
        "bad_research.web.content.fetch_clean.fetch_clean",
        lambda url, *a, **k: _fake_clean_result(url=url),
    )

    res = runner.invoke(
        app, ["fetch", "https://fastapi.tiangolo.com/", "--tag", "fastapi-test", "-j"]
    )
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["ok"] is True
    data = out["data"]
    # Envelope carries at least the contract keys.
    assert {"note_id", "url", "title", "word_count"} <= set(data)
    assert data["url"] == "https://fastapi.tiangolo.com/"
    assert data["title"] == "FastAPI Docs"
    assert data["word_count"] > 0
    assert data["tag"] == "fastapi-test"

    # The note exists on disk, is tagged, and has type=note (what the corpus
    # survey / draft subagents count — there is no NoteType.SOURCE; the survey
    # applies no type filter, it counts by tag).
    note_file = notes_dir / f"{data['note_id']}.md"
    assert note_file.exists()
    body = note_file.read_text(encoding="utf-8")
    assert "fastapi-test" in body
    assert "type: note" in body
    assert "Real cleaned body text" in body


def test_fetch_note_is_findable_by_search_tag(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "bad_research.web.content.fetch_clean.fetch_clean",
        lambda url, *a, **k: _fake_clean_result(url=url),
    )
    runner.invoke(app, ["fetch", "https://fastapi.tiangolo.com/", "--tag", "corp", "-j"])

    res = runner.invoke(app, ["search", "", "--tag", "corp", "-j"])
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["count"] >= 1


# ── bad fetch: SSRF refusal ──────────────────────────────────────────────────────

def test_fetch_refuses_ssrf_url(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    # No fetch mock: assert_url_safe must refuse BEFORE any network call.
    res = runner.invoke(
        app,
        ["fetch", "http://169.254.169.254/latest/meta-data/", "--tag", "x", "-j"],
    )
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["ok"] is False
    assert out["error_code"] == "SSRF_REFUSED"


def test_fetch_refuses_loopback(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["fetch", "http://127.0.0.1:8080/", "--tag", "x", "-j"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["error_code"] == "SSRF_REFUSED"


# ── bad fetch: empty content ─────────────────────────────────────────────────────

def test_fetch_empty_content_is_typed_error(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "bad_research.web.content.fetch_clean.fetch_clean",
        lambda url, *a, **k: _fake_clean_result(url=url, markdown="   "),
    )
    res = runner.invoke(app, ["fetch", "https://example.com/empty", "--tag", "x", "-j"])
    assert res.exit_code == 1
    out = json.loads(res.stdout)
    assert out["error_code"] == "EMPTY_CONTENT"


# ── bad fetch: provenance ─────────────────────────────────────────────────────────

def test_fetch_records_provenance(tmp_path, monkeypatch):
    notes_dir = _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "bad_research.web.content.fetch_clean.fetch_clean",
        lambda url, *a, **k: _fake_clean_result(url=url),
    )
    res = runner.invoke(
        app,
        [
            "fetch", "https://fastapi.tiangolo.com/tutorial/",
            "--tag", "corp",
            "--suggested-by", "seed-note",
            "--suggested-by-reason", "cited as primary source",
            "-j",
        ],
    )
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["data"]["suggested_by"] == "seed-note"

    body = (notes_dir / f"{out['data']['note_id']}.md").read_text(encoding="utf-8")
    # Provenance in frontmatter (round-trips because suggested_by is a NoteMeta field).
    assert "suggested_by: seed-note" in body
    assert "cited as primary source" in body
    # Vault-graph edge: a [[seed-note]] wiki-link in the body so sync indexes the
    # citation-ancestry edge the width-sweep clustering reads.
    assert "[[seed-note]]" in body


# ── bad fetch: tier-max routes through the browse ladder ─────────────────────────

def test_fetch_tier_max_uses_browse_ladder(tmp_path, monkeypatch):
    _init_vault(tmp_path)
    monkeypatch.chdir(tmp_path)

    calls = {}

    class _Res:
        title = "Laddered"
        content = "Body from the tiered browse ladder."
        metadata = {"title": "Laddered", "fetch_provider": "tiered"}
        links: list = []

    def _fake_fetch_tiered(url, *, tier_max, instruction=None, **k):
        calls["tier_max"] = tier_max
        calls["instruction"] = instruction
        return _Res()

    monkeypatch.setattr("bad_research.browse.fetch_tiered", _fake_fetch_tiered)
    # fetch_clean must NOT be called on the ladder path.
    monkeypatch.setattr(
        "bad_research.web.content.fetch_clean.fetch_clean",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetch_clean must not run")),
    )

    res = runner.invoke(
        app,
        [
            "fetch", "https://hard.example.com/",
            "--tag", "corp", "--tier-max", "3",
            "--instruction", "extract the main content", "-j",
        ],
    )
    assert res.exit_code == 0, res.stdout
    assert calls == {"tier_max": 3, "instruction": "extract the main content"}
    out = json.loads(res.stdout)
    assert out["data"]["title"] == "Laddered"
    assert out["data"]["tier_max"] == 3


# ════════════════════════════════════════════════════════════════════════════════
# GAP 2 — funnel keyless-provider cascade + per-provider/per-page failover
# ════════════════════════════════════════════════════════════════════════════════


def test_build_providers_leads_with_keyless_http(monkeypatch):
    """The CLI funnel cascade must LEAD with a keyless HTTP provider so the
    light-mode `[:1]` slice never picks the host-tool provider (which can't run
    in a subprocess)."""
    from bad_research.cli.research import _build_providers

    class _Cfg:
        searxng_endpoint = ""

    provs = _build_providers(_Cfg())
    assert provs, "expected at least one provider"
    # The first (and therefore the light-mode active) provider is the keyless
    # ddgs HTTP lane, NOT the host WebSearch tool adapter.
    assert provs[0].name == "ddgs"
    names = [p.name for p in provs]
    # The host-tool provider may still be present (in-agent path), but never first.
    if "websearch" in names:
        assert names.index("websearch") > names.index("ddgs")


@pytest.mark.asyncio
async def test_fan_out_skips_not_implemented_provider():
    """A provider whose search_ex raises NotImplementedError (the host WebSearch
    tool in a subprocess) is skipped — the surviving keyless provider carries the
    run; the run is NEVER zeroed."""
    from bad_research.funnel.fanout import SearchQuery, fan_out
    from bad_research.web.base import WebResult

    class _HostTool:
        name = "websearch"

        def search_ex(self, q):
            raise NotImplementedError("host WebSearch tool unreachable in subprocess")

    class _Keyless:
        name = "ddgs"

        def search_ex(self, q):
            return [WebResult(url="https://ok.example/1", title="ok", content="body")]

    queries = [SearchQuery(query="fastapi")]
    # Host tool FIRST in the list — it must not abort the fan-out.
    hits = await fan_out(queries, [_HostTool(), _Keyless()])
    assert len(hits) == 1
    assert hits[0].url == "https://ok.example/1"


@pytest.mark.asyncio
async def test_fan_out_not_implemented_only_returns_empty():
    """A fan-out where every provider raises NotImplementedError degrades to an
    empty pool — not a crash."""
    from bad_research.funnel.fanout import SearchQuery, fan_out

    class _HostTool:
        name = "websearch"

        def search_ex(self, q):
            raise NotImplementedError

    hits = await fan_out([SearchQuery(query="x")], [_HostTool()])
    assert hits == []


@pytest.mark.asyncio
async def test_read_top_k_skips_failing_fetch():
    """A single page's fetch failure (e.g. 403) must NOT abort the read wave —
    the survivors are returned, the failure is dropped."""
    from bad_research.funnel.read import read_top_k

    class _Cand:
        def __init__(self, url):
            self.canonical_url = url

    class _Page:
        def __init__(self, url):
            self.url = url
            self.content = "body for " + url
            self.links: list = []

    class _Fetcher:
        def fetch_tiered(self, url, *, tier_max):
            if "boom" in url:
                raise RuntimeError("403 Forbidden")
            return _Page(url)

    ranked = [_Cand("https://ok.example/1"), _Cand("https://boom.example/2"),
              _Cand("https://ok.example/3")]
    pages = await read_top_k(
        ranked, fetcher=_Fetcher(), read_top_k=10, concurrency=2,
        max_chain_depth=0, max_links_per_hub=0, query="q", ceiling=80,
    )
    urls = sorted(p.url for p in pages)
    assert urls == ["https://ok.example/1", "https://ok.example/3"]


def test_vault_store_tags_and_records_stored_ids(tmp_path):
    """VaultStore applies the run's vault_tag to every stored note AND records
    the stored note ids so the standalone funnel can report sources gathered."""
    from bad_research.core.vault import Vault
    from bad_research.funnel.store import VaultStore

    Vault.init(tmp_path, name="t")
    vault = Vault.discover(tmp_path)
    store = VaultStore(vault, tags=["my-run"])
    nid = store.store_note(
        title="A page", body="some body", url="https://ex.com/a", provider="ddgs"
    )
    assert nid in store.stored_note_ids
    body = (vault.notes_dir / f"{nid}.md").read_text(encoding="utf-8")
    assert "my-run" in body
