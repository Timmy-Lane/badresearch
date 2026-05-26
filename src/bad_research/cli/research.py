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

import typer


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
    """Web search providers (Plan 03 cascade survivors). Best-effort: the
    builtin/exa providers when configured, else an empty list (the funnel
    degrades to an honest empty envelope)."""
    try:
        from bad_research.web.base import get_provider

        return [get_provider("builtin")]
    except Exception:
        return []


def _build_tiered_fetcher(cfg: object) -> object | None:
    """Tier 0->3 browse fetcher (Plan 04)."""
    try:
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
    reasoning_effort: str = typer.Option(None, "--reasoning-effort"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run the scraper funnel: fan-out->dedup->rank->read(Tier0-3)->filter->chunk->rerank."""
    if query_file:
        q = Path(query_file).read_text(encoding="utf-8")
    elif query:
        q = query
    else:
        raise typer.BadParameter("provide a query argument or --query-file")
    typer.echo(json.dumps(run_funnel(q, mode=mode, vault_tag=vault_tag), default=str))


# ── retrieve (Task 9/12) — hybrid retrieval top-chunks ───────────────────────
def _build_engine(cfg: object, vault: object) -> object:
    """Construct a keyless FTS-only RetrievalEngine bound to the vault's cache dir.

    The dense vector lane (LanceDB + a [local] embedder) is opt-in — None here by
    default. KR-5 turns it on above the 25k-chunk threshold or when neural_recall=1.
    """
    from bad_research.retrieval.engine import RetrievalEngine

    root = Path(getattr(vault, "root", Path.cwd()))
    base = root / ".bad-research"
    base.mkdir(parents=True, exist_ok=True)
    embedder = _build_embedder(cfg)
    lance_dir = (base / "lance") if embedder is not None else None
    return RetrievalEngine(
        cache_db=base / "semantic_cache.db",
        reranker=_build_reranker(cfg),
        embedder=embedder,
        lance_dir=lance_dir,
    )


def _build_embedder(cfg: object) -> object | None:
    """Keyless default = no neural embedder (FTS-only). The local bi-encoder lane
    ([local]) is opt-in via config.neural_recall — built in KR-5. Returns None
    unless neural recall is explicitly enabled AND the [local] stack imports."""
    if not getattr(cfg, "neural_recall", False):
        return None
    try:
        from bad_research.embed.base import get_embed_provider

        return get_embed_provider("bge-local")
    except ImportError:
        return None  # [local] not installed -> degrade to FTS-only (graceful)


def _build_reranker(cfg: object) -> object:
    """Keyless reranker: get_reranker reads cfg.reranker (default "host" ->
    ClaudeCodeReranker, the host-model LLM-rerank). "local"/"none" also keyless."""
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
    from bad_research.grounding.nli import CrossEncoderNLI
    from bad_research.grounding.verifier import CitationVerifier

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
    verifier = CitationVerifier(nli=CrossEncoderNLI(), llm=get_llm_provider("anthropic", config=cfg))
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
def _uncited_gate(report_path: str, vault_tag: str) -> list[dict]:
    """Run the deterministic no-uncited-claim gate over the report."""
    import sqlite3

    from bad_research.core.vault import Vault
    from bad_research.grounding.anchors import AnchorStore
    from bad_research.grounding.gate import no_uncited_claim_gate

    vault = Vault.discover()
    report_md = Path(report_path).read_text(encoding="utf-8")
    db_path = Path(vault.root) / ".bad-research" / "anchors.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    store = AnchorStore(conn)
    findings = no_uncited_claim_gate(report_md, store)
    return [
        {"sentence": getattr(f, "location", ""), "reason": getattr(f, "failure_mode", "uncited")}
        for f in findings
    ]


def uncited_gate_cmd(
    report: str = typer.Option(..., "--report"),
    vault_tag: str = typer.Option(..., "--vault-tag"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Deterministic ($0) no-uncited-claim ship gate. Non-zero exit when it blocks."""
    uncited = _uncited_gate(report, vault_tag)
    typer.echo(json.dumps({"uncited": uncited}))
    if uncited:
        raise typer.Exit(1)


__all__ = [
    "funnel_gather_cmd",
    "retrieve_cmd",
    "route_cmd",
    "run_funnel",
    "uncited_gate_cmd",
    "verify_citations_cmd",
]
