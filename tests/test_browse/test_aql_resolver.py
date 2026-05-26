"""AqlExtractProvider — AQL resolve against a Snapshot, with ref-grounding. Mock LLM."""

from __future__ import annotations

import json

from bad_research.browse.agent_browser import Snapshot
from bad_research.browse.aql import AqlExtractProvider, resolve_aql
from tests.test_browse.conftest import FakeLLM


def _login_snapshot() -> Snapshot:
    return Snapshot(
        text="@e3 [textbox] Email\n@e4 [textbox] Password\n@e5 [button] Continue",
        refs={
            "e3": {"role": "textbox", "name": "Email"},
            "e4": {"role": "textbox", "name": "Password"},
            "e5": {"role": "button", "name": "Continue"},
        },
    )


def test_resolve_maps_fields_to_grounded_refs_via_llm() -> None:
    # Host model returns a field→ref mapping; resolver keeps only grounded refs.
    llm = FakeLLM([json.dumps({"email_input": "@e3", "submit_button": "@e5"})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(_login_snapshot(),
                       "{ email_input  submit_button }",
                       instruction="find the login fields")
    assert out == {"email_input": "@e3", "submit_button": "@e5"}
    # the host-model prompt embedded the snapshot text + the AQL query
    assert "email_input" in llm.calls[0]["messages"][-1].content


def test_ungrounded_ref_is_dropped() -> None:
    # LLM hallucinates @e99 (not in refs) → grounding drops it; @e3 survives.
    llm = FakeLLM([json.dumps({"email_input": "@e3", "ghost": "@e99"})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(_login_snapshot(), "{ email_input  ghost }")
    assert out == {"email_input": "@e3"}   # ghost dropped (ungrounded)


def test_no_llm_falls_back_to_deterministic_name_match() -> None:
    # No LLM: match AQL field name against snapshot ref names (case/underscore-insensitive).
    prov = AqlExtractProvider(llm=None)
    out = prov.extract(_login_snapshot(), "{ email  password }")
    # 'email' → e3 (name 'Email'), 'password' → e4 (name 'Password')
    assert out["email"] == "@e3"
    assert out["password"] == "@e4"


def test_string_schema_must_be_valid_aql() -> None:
    prov = AqlExtractProvider(llm=None)
    out = prov.extract(_login_snapshot(), "not valid aql")  # missing braces
    assert out == {}    # parse error → graceful empty (never raises)


def test_list_node_resolves_to_list_of_refs() -> None:
    snap = Snapshot(
        text="links",
        refs={
            "e1": {"role": "link", "name": "Home"},
            "e2": {"role": "link", "name": "About"},
            "e3": {"role": "heading", "name": "Title"},
        },
    )
    llm = FakeLLM([json.dumps({"nav_links": ["@e1", "@e2"]})])
    prov = AqlExtractProvider(llm=llm)
    out = prov.extract(snap, "{ nav_links[] }")
    assert out == {"nav_links": ["@e1", "@e2"]}


def test_resolve_aql_function_is_pure() -> None:
    # resolve_aql(ast, snapshot, mapping) grounds a raw mapping with no LLM at all.
    from bad_research.browse.aql import parse_aql
    ast = parse_aql("{ a  b }")
    snap = Snapshot(refs={"e1": {"role": "button", "name": "A"}})
    grounded = resolve_aql(ast, snap, {"a": "@e1", "b": "@e9"})
    assert grounded == {"a": "@e1"}   # b ungrounded → dropped


def test_provider_name() -> None:
    assert AqlExtractProvider(llm=None).name == "aql"
