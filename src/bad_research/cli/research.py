"""Research-pipeline CLI subcommands — JSON-out bridges the skills call via Bash.

Each command is a thin wrapper over a deterministic backend seam (router /
funnel / retrieval / grounding). They emit JSON envelopes the skill prompts
parse. Heavy backends (embedder, NLI, web providers) are imported lazily inside
each function so importing this module (and registering the commands) never
pulls in optional deps — a missing backend fails only when its command runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from bad_research.grounding.anchors import AnchorStore


# ── route (Task 2/5/12) — deterministic, $0, no heavy deps ───────────────────
def route_cmd(
    decomposition: str = typer.Option(..., "--decomposition"),
    apply: bool = typer.Option(False, "--apply"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Classify a Step-1 decomposition into a pipeline route (agentic-fast|light|full)."""
    from bad_research.skills.router import classify_route, route_reason

    path = Path(decomposition)
    decomp = json.loads(path.read_text(encoding="utf-8"))
    route = classify_route(decomp)
    if apply:
        decomp["route"] = route
        path.write_text(json.dumps(decomp, indent=2), encoding="utf-8")
    out = {"route": route, "reason": route_reason(decomp), "applied": apply}
    typer.echo(json.dumps(out) if json_output else f"route: {route}")


# ── funnel-gather (Task 6/9/12) — the §6 scraper funnel ──────────────────────
def _build_providers(cfg: object) -> list:
    """Keyless web providers (KR-2). Default = the host WebSearch tool adapter +
    the ddgs multi-engine lib; an optional self-host SearXNG when configured.
    Intent-routed scholarly verticals are added by the skill (route_query), not
    here — this builder supplies the always-on keyless breadth sources. Every
    provider is cost_per_search=0.0, zero key. Degrades to [] on import error."""
    provs: list[Any] = []
    try:
        from bad_research.web.search.base import DdgsProvider, WebSearchToolProvider

        provs.append(WebSearchToolProvider())
        provs.append(DdgsProvider())
    except Exception:
        return []
    endpoint = getattr(cfg, "searxng_endpoint", "") or ""
    if endpoint:
        try:
            from bad_research.web.search.base import SearxngProvider

            provs.append(SearxngProvider(endpoint=endpoint))
        except Exception:
            pass
    return provs


def _build_tiered_fetcher(cfg: object) -> object | None:
    """Keyless 4-rung browse fetcher (KR-4): httpx -> crawl4ai -> agent-browser
    (lightpanda) -> agent-browser (chrome). No Browserbase/Browser-Use rung.
    The ladder reads the default browse engine from config."""
    from typing import Literal

    try:
        from bad_research.browse.ladder import TieredFetcher

        # Normalize to the Literal the ladder accepts; any non-"chrome" value
        # defaults to lightpanda (the keyless rung-2.5 default, dossier 14 §12.5).
        engine: Literal["lightpanda", "chrome"] = (
            "chrome" if getattr(cfg, "browse_engine", "lightpanda") == "chrome" else "lightpanda"
        )
        return TieredFetcher(engine=engine)
    except TypeError:
        # TieredFetcher() may not yet accept engine= on an older KR-4 build.
        from bad_research.browse.ladder import TieredFetcher

        return TieredFetcher()
    except Exception:
        return None


def _build_postfetch(cfg: object) -> object:
    """Post-fetch junk/language filter (Plan 05). Default: keep everything."""
    try:
        from bad_research.quality.content_filter import postfetch_reject_reason

        return postfetch_reject_reason
    except Exception:
        return lambda r: None


def run_funnel(query: str, *, mode: str, vault_tag: str) -> dict:
    """Build FunnelDeps from config + run the FROZEN async gather(), then collapse
    the returned list[Chunk] into a FunnelEnvelope dict. Shared by CLI + MCP.

    Returns {"note_ids", "top_chunks", "n_read"}. The model reads top_chunks only.
    """
    import asyncio
    from dataclasses import asdict, is_dataclass

    from bad_research.config import BadResearchConfig
    from bad_research.core.vault import Vault
    from bad_research.funnel import gather
    from bad_research.funnel.orchestrator import FunnelDeps
    from bad_research.funnel.store import VaultStore

    cfg = BadResearchConfig.load()
    vault = Vault.discover()
    engine = _build_engine(cfg, vault)
    deps = FunnelDeps(
        providers=_build_providers(cfg),
        fetcher=_build_tiered_fetcher(cfg),
        postfetch_filter=_build_postfetch(cfg),
        vault=VaultStore(vault),
        retrieval=engine,
    )
    norm_mode = "full" if mode == "full" else "light"
    chunks = asyncio.run(gather(query, mode=norm_mode, deps=deps))

    note_ids: list[str] = []
    seen: set[str] = set()
    top_chunks: list[dict] = []
    for c in chunks:
        nid = getattr(c, "note_id", None)
        if nid is not None and nid not in seen:
            seen.add(nid)
            note_ids.append(nid)
        top_chunks.append(asdict(c) if is_dataclass(c) else dict(getattr(c, "__dict__", {})))
    return {"note_ids": note_ids, "top_chunks": top_chunks, "n_read": len(note_ids)}


def funnel_gather_cmd(
    query: str = typer.Argument(None),
    query_file: str = typer.Option(None, "--query-file"),
    search_plan: str = typer.Option(None, "--search-plan"),
    mode: str = typer.Option("light", "--mode"),
    vault_tag: str = typer.Option("", "--vault-tag"),
    max_queries: int = typer.Option(None, "--max-queries"),
    read_top_k: int = typer.Option(None, "--read-top-k"),
    reasoning_effort: str = typer.Option(None, "--reasoning-effort", "--effort"),
    max_tokens: int = typer.Option(None, "--max-tokens"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the scraper funnel: fan-out->dedup->rank->read(rung0-3)->filter->chunk->rerank.

    --reasoning-effort (minimal|low|medium|high) nudges the route + per-stage fan-out
    via skills/router.effort_overrides; --max-tokens sets the per-run ceiling the
    orchestrator degrades against. Both default to the config's tier behaviour.
    """
    from bad_research.skills.router import effort_overrides

    if query_file:
        q = Path(query_file).read_text(encoding="utf-8")
    elif query:
        q = query
    else:
        raise typer.BadParameter("provide a query argument or --query-file")
    # An explicit --reasoning-effort pins the route (the OpenAI continuum); else the
    # caller's --mode stands. This wires the previously-ignored stub flag.
    eff_mode = mode
    ov = effort_overrides(reasoning_effort)
    if ov is not None:
        eff_mode = ov["route"]
    typer.echo(json.dumps(run_funnel(q, mode=eff_mode, vault_tag=vault_tag), default=str))


# ── retrieve (Task 9/12) — hybrid retrieval top-chunks ───────────────────────
def _build_engine(cfg: object, vault: object) -> object:
    """Construct a keyless RetrievalEngine bound to the vault's cache dir. FTS5/BM25
    is the only mandatory index (KR-5); the LanceDB vector lane is wired only when a
    local embedder is present.

    The dense lane is opt-in via `cfg.neural_recall` (the `[local]` extra): when it
    is True, `_build_embedder` returns the bge-small bi-encoder and this constructor
    threads a `lance_dir`; when it is False (the keyless default), the embedder is
    None and retrieval is FTS-only. (The 25k-chunk auto-enable
    `NEURAL_RECALL_VAULT_THRESHOLD` is a vault-size policy not wired in this builder
    — it would belong to the index/vault layer, not the per-call engine factory.)
    """
    from bad_research.retrieval.engine import RetrievalEngine

    root = Path(getattr(vault, "root", Path.cwd()))
    base = root / ".bad-research"
    base.mkdir(parents=True, exist_ok=True)
    embedder = _build_embedder(cfg)
    reranker = _build_reranker(cfg)
    lance_dir = (base / "lance") if embedder is not None else None
    return RetrievalEngine(
        cache_db=base / "semantic_cache.db",
        reranker=reranker,
        embedder=embedder,
        lance_dir=lance_dir,
    )


def _build_embedder(cfg: object) -> object | None:
    """Keyless default: NO embedder (FTS5/BM25-only recall, KR-5). The local
    bi-encoder lane is opt-in: only when config.neural_recall is True (the [local]
    extra). Cohere is GONE."""
    if not getattr(cfg, "neural_recall", False):
        return None
    try:
        from bad_research.embed.base import get_embed_provider

        return get_embed_provider("bge-local")
    except Exception:
        return None


def _build_reranker(cfg: object) -> object:
    """Keyless default reranker = ClaudeCodeReranker (host-model LLM-rerank, KR-5).
    config.reranker selects host|local|none; the factory resolves it. Cohere is GONE."""
    from bad_research.retrieval.rerank import get_reranker

    return get_reranker(cfg)


def retrieve_cmd(
    query: str = typer.Argument(...),
    mode: str = typer.Option("full", "--mode"),
    top_k: int = typer.Option(20, "--top-k"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Hybrid retrieval: vector+BM25 fuse (alpha=0.7) -> rerank -> 0.70 gate. Returns top_k Chunks."""
    from dataclasses import asdict

    from bad_research.config import BadResearchConfig
    from bad_research.core.vault import Vault

    cfg = BadResearchConfig.load()
    vault = Vault.discover()
    engine = _build_engine(cfg, vault)
    norm_mode = "full" if mode == "full" else "light"
    chunks = engine.search(query, mode=norm_mode, top_k=top_k)
    typer.echo(json.dumps([asdict(c) for c in chunks], default=str))


# ── verify-citations (Task 8/11/12) — backward grounding ─────────────────────
def _verify_report(report_path: str, vault_tag: str) -> list[dict]:
    """Adapter: load report + AnchorStore + note bodies, run CitationVerifier."""
    import sqlite3
    from dataclasses import asdict, is_dataclass

    from bad_research.config import BadResearchConfig
    from bad_research.core.vault import Vault
    from bad_research.grounding.anchors import AnchorStore
    from bad_research.grounding.verifier import CitationVerifier, default_nli

    cfg = BadResearchConfig.load()
    vault = Vault.discover()
    report_md = Path(report_path).read_text(encoding="utf-8")
    db_path = Path(vault.root) / ".bad-research" / "anchors.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)

    note_bodies: dict[str, str] = {}
    notes_dir = Path(vault.root) / "research" / "notes"
    if notes_dir.is_dir():
        for f in notes_dir.glob("*.md"):
            note_bodies[f.stem] = f.read_text(encoding="utf-8")

    from bad_research.llm.base import get_llm_provider

    # get_llm_provider(name, **kwargs) forwards kwargs to AnthropicProvider, whose
    # signature is AnthropicProvider(api_key=None, config=None) — pass cfg via config=.
    # default_nli() auto-selects the real cross-encoder entailment lane when the
    # [local] stack is installed, else the keyless citation-present no-op (no torch).
    verifier = CitationVerifier(nli=default_nli(), llm=get_llm_provider("anthropic", config=cfg))
    result = verifier.verify(report_md, store, note_bodies)
    findings = getattr(result, "findings", result)
    out = []
    for f in findings:
        out.append(asdict(f) if is_dataclass(f) else dict(getattr(f, "__dict__", {})))
    return out


def verify_citations_cmd(
    report: str = typer.Option(..., "--report"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the CitationVerifier over a report. Returns per-sentence dispositions."""
    typer.echo(json.dumps({"results": _verify_report(report, vault_tag)}, default=str))


# ── uncited-gate (Task 9/12) — deterministic ship-block, $0 ──────────────────
def _standalone_store_from_bodies(note_bodies: dict[str, str]) -> AnchorStore:
    """An in-memory AnchorStore seeded from `{note_id: body}` — the standalone
    path (no pre-populated vault, mirrors recitation-gate's --note-bodies). Each
    body becomes a verified anchor keyed by BOTH its note_id (so `[[note-id]]`
    wiki-links resolve) AND its 1-based ordinal (so numeric `[N]` resolve — `[1]`
    is the FIRST key in the JSON map's insertion order, `[2]` the second, …). The
    whole body is the quoted_support, so Tier-A byte-identity holds if the
    verifier is ever run over the same store. verified=1: the standalone gate
    treats a provided source as authoritative (its job is "is there a real
    citation", not "did Tier B pass")."""
    import sqlite3

    from bad_research.grounding.anchors import AnchorStore, ClaimAnchor

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    store.init_schema()
    for idx, (note_id, body) in enumerate(note_bodies.items(), start=1):
        body = body or ""
        # [[note-id]] anchor: anchor_id is the note_id itself so gate.get(note_id) hits.
        wiki = ClaimAnchor(
            note_id=note_id, char_start=0, char_end=len(body),
            claim="", quoted_support=body, verified=1, anchor_id=note_id,
        )
        store.upsert(wiki)
        # [N] anchor: anchor_id is the 1-based ordinal so gate.get("1") hits. A
        # separate row (distinct PK) pointing at the same note/body.
        numeric = ClaimAnchor(
            note_id=note_id, char_start=0, char_end=len(body),
            claim="", quoted_support=body, verified=1, anchor_id=str(idx),
        )
        store.upsert(numeric)
    return store


def _uncited_gate(report_path: str, vault_tag: str, note_bodies_path: str | None) -> list[dict[str, Any]]:
    """Run the deterministic no-uncited-claim gate over the report.

    Standalone-safe: `--note-bodies` (a JSON `{note_id: body}` map) seeds an
    in-memory store with no vault needed; otherwise the vault's anchors.db is
    used. The schema is always auto-initialized so a missing `claim_anchors`
    table yields a clean "0 anchors" result instead of an OperationalError, and a
    missing vault degrades to an empty store rather than crashing."""
    import sqlite3

    from bad_research.grounding.anchors import AnchorStore
    from bad_research.grounding.gate import no_uncited_claim_gate

    report_md = Path(report_path).read_text(encoding="utf-8")

    if note_bodies_path:
        bodies = json.loads(Path(note_bodies_path).read_text(encoding="utf-8"))
        store: AnchorStore = _standalone_store_from_bodies(bodies)
    else:
        # Vault path; if there is no vault (standalone, no --note-bodies), fall
        # back to an empty in-memory store so the gate still runs (every factual
        # sentence reads as uncited, which is the honest answer with no sources).
        from bad_research.core.vault import Vault, VaultError

        try:
            vault = Vault.discover()
            db_path = Path(vault.root) / ".bad-research" / "anchors.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
        except VaultError:
            conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        store = AnchorStore(conn)
        # Auto-init: a vault DB that predates the grounding tables (or a fresh
        # in-memory DB) has no claim_anchors table. init_schema is idempotent.
        store.init_schema()

    findings = no_uncited_claim_gate(report_md, store)
    return [
        {"sentence": getattr(f, "location", ""), "reason": getattr(f, "failure_mode", "uncited")}
        for f in findings
    ]


def uncited_gate_cmd(
    report: str = typer.Option(..., "--report"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    note_bodies: str = typer.Option(
        None, "--note-bodies", "--sources",
        help="JSON {note_id: body} map. `[[note-id]]` resolves by id; numeric `[N]` "
             "resolves to the N-th key in insertion order ([1] = first key).",
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Deterministic ($0) no-uncited-claim ship gate. Non-zero exit when it blocks.

    Standalone (outside Claude Code): pass `--note-bodies`/`--sources` (a JSON
    `{note_id: body}` map) to resolve `[N]`/`[[note-id]]` citations with no
    pre-populated vault — mirrors recitation-gate. Numeric `[N]` resolves
    positionally ([1] = first key in the map). With neither a vault nor
    --note-bodies, the gate auto-inits an empty store (clean "0 anchors")."""
    uncited = _uncited_gate(report, vault_tag, note_bodies)
    typer.echo(json.dumps({"uncited": uncited}))
    if uncited:
        raise typer.Exit(1)


# ── grade-report (Stage 12.5) — in-pipeline grader, single host-model call ────
def grade_report_cmd(
    report: str = typer.Option(..., "--report"),
    corpus: str = typer.Option(..., "--corpus"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Grade a report on the 5 axes + emit patcher-shaped findings (Stage 12.5).

    --corpus is a JSON file: a list of {note_id, url, text} dicts (the
    evidence-digest the report had access to). Returns {passed, scores, overall,
    findings:[{failure_mode, severity, location, recommendation}]} for the grader
    loop to feed the patcher. The verdict's findings join critic-findings-grader.json.
    """
    from bad_research.config import BadResearchConfig
    from bad_research.llm.base import get_llm_provider
    from bad_research.quality.grader import Grader

    cfg = BadResearchConfig.load()
    report_md = Path(report).read_text(encoding="utf-8")
    corpus_rows = json.loads(Path(corpus).read_text(encoding="utf-8"))
    grader = Grader(provider=get_llm_provider("anthropic", config=cfg))
    # the query is embedded in the report's H1; the grader reads the report directly.
    query = report_md.splitlines()[0].lstrip("# ").strip() if report_md else ""
    verdict = grader.grade(query, report_md, corpus_rows)
    typer.echo(json.dumps(verdict.to_dict(), default=str))


# ── recitation-gate (Stage 16) — verbatim-copy detector, $0 deterministic ─────
def recitation_gate_cmd(
    report: str = typer.Option(..., "--report"),
    note_bodies: str = typer.Option(..., "--note-bodies"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Deterministic ($0) recitation gate. --note-bodies is a JSON file mapping
    note_id -> body markdown. Flags sentences that copy a source verbatim. A
    `major` finding (NOT a ship-block — unlike uncited-gate); exit 0 always."""
    from bad_research.quality.recitation import recitation_findings

    report_md = Path(report).read_text(encoding="utf-8")
    bodies = json.loads(Path(note_bodies).read_text(encoding="utf-8"))
    findings = recitation_findings(report_md, bodies)
    typer.echo(json.dumps({
        "recitation": [
            {"failure_mode": f.failure_mode, "severity": f.severity,
             "location": f.location, "recommendation": f.recommendation}
            for f in findings
        ]
    }))


__all__ = [
    "funnel_gather_cmd",
    "grade_report_cmd",
    "recitation_gate_cmd",
    "retrieve_cmd",
    "route_cmd",
    "run_funnel",
    "uncited_gate_cmd",
    "verify_citations_cmd",
]
