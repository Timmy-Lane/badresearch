"""The AgentBrowserProvider ReAct browse loop. FakeRunner feeds canned snapshot/eval stdout."""

from __future__ import annotations

import pytest

import bad_research.browse.agent_browser as ab
from bad_research.browse.agent_browser import (
    ACT_SYSTEM_PROMPT,
    AGENT_LOOP_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    OBSERVE_SYSTEM_PROMPT,
    AgentBrowserProvider,
    BrowseStep,
)
from bad_research.web.base import WebResult
from tests.test_browse.conftest import (
    EMPTY_SNAPSHOT_JSON,
    SNAPSHOT_JSON,
    FakeRunner,
)


@pytest.fixture(autouse=True)
def _cli_present(monkeypatch):
    """The loop tests inject a FakeRunner (the CLI stand-in); default the availability
    gate to True so the ReAct loop runs without the real agent-browser binary. The
    `test_cli_absent_*` test overrides this with its own monkeypatch to False."""
    monkeypatch.setattr(ab, "is_available", lambda program="agent-browser": True)


def test_provider_name() -> None:
    assert AgentBrowserProvider(runner=FakeRunner()).name == "agent-browser"


def test_open_snapshot_returns_webresult_with_snapshot_text() -> None:
    # open → wait → snapshot. No interaction steps → result content = snapshot text.
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    result = prov.browse("https://example.com/login", "read the login page")
    assert isinstance(result, WebResult)
    assert "@e5 [button" in result.content
    assert result.metadata["engine"] == "chrome"
    # the very first command opened the right URL
    assert runner.argvs()[0][:4] == ["agent-browser", "--engine", "chrome", "open"]
    assert runner.argvs()[0][-1] == "https://example.com/login"


def test_browse_executes_supplied_steps_then_resnapshots() -> None:
    # A login flow: fill @e3, fill @e4, click @e5 — re-snapshot after the click.
    runner = FakeRunner(route={
        "open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON,
        "fill": "{}", "click": "{}",
    })
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    steps = [
        BrowseStep("fill", "@e3", "user@example.com"),
        BrowseStep("fill", "@e4", "secret"),
        BrowseStep("click", "@e5"),
    ]
    prov.browse("https://example.com/login", "log in", steps=steps)
    cmds = [argv[3] for argv in runner.argvs()]  # the command word (after engine flag)
    assert cmds.count("fill") == 2
    assert cmds.count("click") == 1
    # at least two snapshots: initial perception + a re-snapshot after the click
    assert cmds.count("snapshot") >= 2


def test_lightpanda_empty_snapshot_falls_back_to_chrome() -> None:
    # lightpanda returns an empty snapshot → provider retries the open+snapshot on chrome.
    runner = FakeRunner(replies=[
        "{}",                  # lightpanda open
        "{}",                  # lightpanda wait
        EMPTY_SNAPSHOT_JSON,   # lightpanda snapshot → empty → fall back
        "{}",                  # chrome open
        "{}",                  # chrome wait
        SNAPSHOT_JSON,         # chrome snapshot → good
    ])
    prov = AgentBrowserProvider(engine="lightpanda", runner=runner)
    result = prov.browse("https://spa.example/", "read the page")
    assert result.metadata["engine"] == "chrome"            # fell back
    assert "@e5 [button" in result.content
    # the chrome retry re-issued an open with --engine chrome
    engines_used = [argv[2] for argv in runner.argvs()]
    assert "lightpanda" in engines_used and "chrome" in engines_used


def test_step_grounding_skips_refs_absent_from_snapshot() -> None:
    # A step targeting @e99 (not in the snapshot refs) is skipped (grounding), no crash.
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON,
                               "click": "{}"})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.browse("https://example.com/login", "click ghost",
                steps=[BrowseStep("click", "@e99")])
    cmds = [argv[3] for argv in runner.argvs()]
    assert cmds.count("click") == 0   # ungrounded ref → never clicked


def test_cli_absent_returns_empty_webresult_no_raise(monkeypatch) -> None:
    import bad_research.browse.agent_browser as ab
    monkeypatch.setattr(ab, "is_available", lambda program="agent-browser": False)
    prov = AgentBrowserProvider(engine="chrome", runner=FakeRunner())
    result = prov.browse("https://x.test", "do stuff")
    assert isinstance(result, WebResult)
    assert result.content == ""
    assert result.metadata.get("unavailable") is True


def test_stagehand_prompts_are_verbatim_nonempty() -> None:
    # The four prompts ship as constants for the skill to embed (dossier 14 §5, §4.1).
    assert "automate the browser by finding elements" in ACT_SYSTEM_PROMPT
    assert "EXTRACT ALL OF THE INFORMATION" in EXTRACT_SYSTEM_PROMPT
    assert "observe" in OBSERVE_SYSTEM_PROMPT.lower()
    assert "agent_browser tool" in AGENT_LOOP_SYSTEM_PROMPT or \
           "agent-browser" in AGENT_LOOP_SYSTEM_PROMPT


def test_state_flag_threads_to_open_and_forces_chrome() -> None:
    # An authed browse (state given) must run on chrome (lightpanda blocks --state).
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="lightpanda", runner=runner)
    result = prov.browse("https://src.example/article/1", "read it",
                         state="/auth/src.json")
    assert result.metadata["engine"] == "chrome"   # forced
    open_argv = runner.argvs()[0]
    assert "--state" in open_argv and "/auth/src.json" in open_argv
    assert open_argv[2] == "chrome"


def test_headers_flag_threads_through() -> None:
    runner = FakeRunner(route={"open": "{}", "wait": "{}", "snapshot": SNAPSHOT_JSON})
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.browse("https://api.example/", "read",
                headers='{"Authorization":"Bearer t"}')
    open_argv = runner.argvs()[0]
    assert "--headers" in open_argv
    assert '{"Authorization":"Bearer t"}' in open_argv


def test_save_state_builds_state_save_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.save_state("/auth/src.json")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "state", "save", "/auth/src.json",
    ]


def test_cookies_set_curl_builds_argv() -> None:
    runner = FakeRunner(replies=["{}"])
    prov = AgentBrowserProvider(engine="chrome", runner=runner)
    prov.cookies_set_curl("/auth/src.curl")
    assert runner.last() == [
        "agent-browser", "--engine", "chrome", "cookies", "set", "--curl", "/auth/src.curl",
    ]
