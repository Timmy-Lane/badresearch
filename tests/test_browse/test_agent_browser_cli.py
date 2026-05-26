"""argv construction for the agent-browser CLI seam. NO real subprocess — FakeRunner only."""

from __future__ import annotations

from bad_research.browse.agent_browser import _AgentBrowserCLI
from tests.test_browse.conftest import SNAPSHOT_JSON, FakeRunner


def test_open_builds_open_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.open("https://x.test")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "open", "https://x.test"]


def test_snapshot_builds_interactive_json_argv() -> None:
    runner = FakeRunner(replies=[SNAPSHOT_JSON])
    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    out = cli.snapshot(interactive=True)
    assert runner.last() == [
        "agent-browser", "--engine", "lightpanda", "snapshot", "-i", "--json",
    ]
    assert out == SNAPSHOT_JSON


def test_click_uses_ref() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.click("@e5")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "click", "@e5"]


def test_fill_quotes_value_as_separate_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.fill("@e3", "user@example.com")
    # value is its own argv element (no shell quoting needed — argv list, not a string)
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "fill", "@e3", "user@example.com",
    ]


def test_press_key() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.press("Enter")
    assert runner.last() == ["agent-browser", "--engine", "chrome", "press", "Enter"]


def test_eval_stdin_passes_js_on_stdin_not_argv() -> None:
    runner = FakeRunner(replies=['[{"name":"x"}]'])
    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    js = "Array.from(document.querySelectorAll('h2')).map(e=>e.innerText)"
    out = cli.eval_js(js)
    assert runner.last() == ["agent-browser", "--engine", "lightpanda", "eval", "--stdin"]
    # the JS is delivered on stdin, recorded separately by the runner
    assert runner.stdin == js
    assert out == '[{"name":"x"}]'


def test_wait_load_networkidle() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.wait_load("networkidle")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "wait", "--load", "networkidle",
    ]


def test_session_and_state_global_flags_threaded() -> None:
    runner = FakeRunner(replies=["{}"])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner,
                           session="job1", state="/auth/src.json")
    cli.open("https://x.test")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome",
        "--session", "job1", "--state", "/auth/src.json",
        "open", "https://x.test",
    ]


def test_lightpanda_engine_sets_telemetry_env() -> None:
    captured = {}

    def runner(argv, *, timeout=None, env=None, stdin=None):
        captured["env"] = env
        return (0, "{}", "")

    cli = _AgentBrowserCLI(engine="lightpanda", runner=runner)
    cli.open("https://x.test")
    assert captured["env"]["LIGHTPANDA_DISABLE_TELEMETRY"] == "true"


def test_network_requests_xhr_filter() -> None:
    runner = FakeRunner(replies=['{"data":[]}'])
    cli = _AgentBrowserCLI(engine="chrome", runner=runner)
    cli.network_requests(types="xhr,fetch")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome",
        "network", "requests", "--type", "xhr,fetch", "--json",
    ]
