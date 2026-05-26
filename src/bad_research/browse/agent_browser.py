"""AgentBrowserProvider — keyless agentic browse on the local `agent-browser` CLI.

agent-browser (vercel-labs/agent-browser) is a native Rust CLI that drives a LOCAL
headless Chrome-for-Testing (or `--engine lightpanda`) over CDP. It is keyless: the
only keyed surfaces are `-p <cloud-provider>` and the built-in `chat` command, both of
which we never use (dossier 14 §1, §9). Claude Code (the host model) IS the agent brain
— it reasons over the @eN accessibility-snapshot text and supplies the next action; no
paid LLM call is ever made (dossier 14 §4).

This module:
  * _AgentBrowserCLI  — builds argv vectors + runs them via an injectable runner.
  * Snapshot          — parses `snapshot -i --json` stdout into {text, refs} (Task 3).
  * AgentBrowserProvider — the snapshot/ReAct browse loop returning WebResult (Task 4).
  * Stagehand act/extract/observe prompt constants (verbatim, dossier 14 §5).

agent-browser/lightpanda are EXTERNAL CLIs (NOT pip deps). `is_available()` gates
construction so the ladder degrades to crawl4ai/httpx when they are absent.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

# ---- frozen constants (INTERFACES_KEYLESS §8 + dossier 14) ----
DEFAULT_MAX_STEPS = 12             # INTERFACES_KEYLESS §4.3 Protocol default
WAIT_TIMEOUT_MS = 25_000           # dossier 14 §3.5 (below the 30s IPC read timeout)
CLI_TIMEOUT_S = 60                 # dossier 14 §4.1 (chat.rs:226 tool timeout)
AXTREE_MAX_CHARS = 280_000         # dossier 14 §5.4 chunking heuristic
MIN_REFS_FOR_NONEMPTY = 2          # dossier 14 §12.5 lightpanda→chrome fallback floor
DEFAULT_ENGINE: Literal["lightpanda", "chrome"] = "lightpanda"
AB_PROGRAM = "agent-browser"

# A subprocess runner: (argv, *, timeout, env, stdin) -> (returncode, stdout, stderr).
Runner = Callable[..., tuple[int, str, str]]


def _default_runner(argv: list[str], *, timeout: float | None = None,
                    env: dict | None = None, stdin: str | None = None) -> tuple[int, str, str]:
    """The production runner: subprocess.run. Captures stdout/stderr text. Never raises on
    non-zero exit (the caller inspects returncode)."""
    proc = subprocess.run(  # noqa: S603 — argv list, no shell
        argv, capture_output=True, text=True, timeout=timeout,
        env=env, input=stdin,
    )
    return (proc.returncode, proc.stdout or "", proc.stderr or "")


def is_available(program: str = AB_PROGRAM) -> bool:
    """True iff the agent-browser CLI is on PATH (detect-and-degrade contract)."""
    return shutil.which(program) is not None


def _runner_accepts_stdin(runner: Runner) -> bool:
    """Best-effort: does the runner accept a `stdin=` kwarg? Default runner & FakeRunner do."""
    try:
        sig = inspect.signature(runner)
    except (TypeError, ValueError):
        return False
    return "stdin" in sig.parameters or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )


class _AgentBrowserCLI:
    """Builds + runs agent-browser command argv. The runner is injectable so tests assert
    the constructed argv and feed canned stdout (NO real subprocess in tests)."""

    def __init__(
        self,
        *,
        engine: Literal["lightpanda", "chrome"] = DEFAULT_ENGINE,
        runner: Runner | None = None,
        session: str | None = None,
        state: str | None = None,
        headers: str | None = None,
        program: str = AB_PROGRAM,
        timeout_s: float = CLI_TIMEOUT_S,
    ) -> None:
        self.engine = engine
        self._runner = runner or _default_runner
        self.session = session
        self.state = state
        self.headers = headers
        self.program = program
        self.timeout_s = timeout_s

    # ---- argv prefix: program + global flags (order is stable, asserted by tests) ----
    def _prefix(self) -> list[str]:
        argv = [self.program, "--engine", self.engine]
        if self.session:
            argv += ["--session", self.session]
        if self.state:
            argv += ["--state", self.state]
        if self.headers:
            argv += ["--headers", self.headers]
        return argv

    def _env(self) -> dict | None:
        if self.engine == "lightpanda":
            env = dict(os.environ)
            env["LIGHTPANDA_DISABLE_TELEMETRY"] = "true"  # dossier 14 §12.1
            return env
        return None

    def _run(self, *args: str, stdin: str | None = None) -> str:
        argv = self._prefix() + list(args)
        env = self._env()
        # Pass stdin only when the runner accepts it; otherwise fall back to argv-only.
        if _runner_accepts_stdin(self._runner):
            rc, out, _err = self._runner(argv, timeout=self.timeout_s, env=env, stdin=stdin)
        else:
            rc, out, _err = self._runner(argv, timeout=self.timeout_s, env=env)
        return out

    # ---- lifecycle / nav (dossier 14 §3.1) ----
    def open(self, url: str) -> str:
        return self._run("open", url)

    def close(self, *, all_sessions: bool = False) -> str:
        return self._run("close", "--all") if all_sessions else self._run("close")

    # ---- perception (dossier 14 §3.2) ----
    def snapshot(self, *, interactive: bool = True, compact: bool = False,
                 links: bool = False, scope: str | None = None) -> str:
        args = ["snapshot"]
        if interactive:
            args.append("-i")
        if compact:
            args.append("-c")
        if links:
            args.append("-u")
        if scope:
            args += ["-s", scope]
        args.append("--json")
        return self._run(*args)

    def get_text(self, ref: str) -> str:
        return self._run("get", "text", ref)

    def get_attr(self, ref: str, attr: str) -> str:
        return self._run("get", "attr", ref, attr)

    def eval_js(self, js: str) -> str:
        """Run arbitrary JS in the page via `eval --stdin` (the deterministic extraction
        escape hatch, dossier 14 §5.2 Mode B). JS goes on stdin, NOT argv."""
        return self._run("eval", "--stdin", stdin=js)

    # ---- interaction (dossier 14 §3.3) ----
    def click(self, ref: str) -> str:
        return self._run("click", ref)

    def fill(self, ref: str, value: str) -> str:
        return self._run("fill", ref, value)

    def type_text(self, ref: str, value: str) -> str:
        return self._run("type", ref, value)

    def press(self, key: str) -> str:
        return self._run("press", key)

    def select(self, ref: str, *values: str) -> str:
        return self._run("select", ref, *values)

    # ---- wait (dossier 14 §3.5) ----
    def wait_load(self, state: str = "networkidle") -> str:
        return self._run("wait", "--load", state)

    def wait_text(self, text: str) -> str:
        return self._run("wait", "--text", text)

    def wait_url(self, pattern: str) -> str:
        return self._run("wait", "--url", pattern)

    def wait_selector(self, sel: str) -> str:
        return self._run("wait", sel)

    # ---- network (XHR-JSON shortcut, dossier 14 §7) ----
    def network_requests(self, *, types: str = "xhr,fetch") -> str:
        return self._run("network", "requests", "--type", types, "--json")

    # ---- auth (dossier 14 §8/§13) ----
    def state_save(self, path: str) -> str:
        return self._run("state", "save", path)

    def cookies_set_curl(self, curl_file: str) -> str:
        return self._run("cookies", "set", "--curl", curl_file)


# ============================================================ Snapshot (@eN tree)
def normalize_ref(ref: str) -> str:
    """Accept `@e1`, `ref=e1`, or bare `e1` → canonical `e1` (dossier 14 §2.3 parse_ref)."""
    r = ref.strip()
    if r.startswith("@"):
        r = r[1:]
    if r.startswith("ref="):
        r = r[len("ref="):]
    return r


@dataclass
class Snapshot:
    """A parsed agent-browser accessibility snapshot. `refs` is the grounding source:
    a ref is valid iff its normalized id is a key here (dossier 14 §6.3 / §10B)."""

    text: str = ""
    refs: dict[str, dict] = field(default_factory=dict)
    title: str = ""
    url: str = ""

    @property
    def is_empty(self) -> bool:
        """Implausibly empty → triggers the lightpanda→chrome fallback (dossier 14 §12.5)."""
        return len(self.refs) < MIN_REFS_FOR_NONEMPTY

    def has_ref(self, ref: str) -> bool:
        return normalize_ref(ref) in self.refs

    def find_refs_by_role(self, role: str) -> list[str]:
        return [f"@{rid}" for rid, meta in self.refs.items() if meta.get("role") == role]


_TITLE_RE = re.compile(r"^Page:\s*(.+)$", re.MULTILINE)
_URL_RE = re.compile(r"^URL:\s*(\S+)$", re.MULTILINE)


def parse_snapshot(stdout: str) -> Snapshot:
    """Parse `snapshot -i --json` stdout into a Snapshot. Tolerant: malformed JSON or
    success:false → empty Snapshot (never raises) so the loop/ladder can degrade."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return Snapshot()
    if not isinstance(payload, dict) or not payload.get("success"):
        return Snapshot()
    data = payload.get("data") or {}
    text = data.get("snapshot") or ""
    raw_refs = data.get("refs") or {}
    refs = {normalize_ref(k): v for k, v in raw_refs.items() if isinstance(v, dict)}
    title_m = _TITLE_RE.search(text)
    url_m = _URL_RE.search(text)
    return Snapshot(
        text=text,
        refs=refs,
        title=title_m.group(1).strip() if title_m else "",
        url=url_m.group(1).strip() if url_m else "",
    )
