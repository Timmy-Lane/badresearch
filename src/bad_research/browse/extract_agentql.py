"""AgentQLExtractProvider — Tier-2 typed extraction via AgentQL REST query-data.

The AQL query string IS the schema (dossier 03 §2.1). JSON-Schema dicts are translated to
AQL: object->{}, array->[], numeric/boolean leaf->field(type). Deterministic ref-grounding +
1 corrective retry run server-side (dossier 03 §2.4) — this client only sends the query.
Key-gated by AGENTQL_API_KEY; any HTTP failure degrades to {} (never raises).
"""

from __future__ import annotations

import os
from typing import Any

from bad_research.web.base import WebResult

AGENTQL_ENDPOINT = "https://api.agentql.com/v1/query-data"
_TYPE_HINT = {"integer": "integer", "number": "float", "boolean": "boolean"}


def json_schema_to_aql(schema: dict[str, Any]) -> str:
    """Translate a JSON-Schema object into an AgentQL query string."""

    def render_props(props: dict[str, Any]) -> str:
        fields = []
        for name, spec in props.items():
            spec = spec or {}
            t = spec.get("type")
            if t == "object":
                fields.append(f"{name} {{ {render_props(spec.get('properties', {}))} }}")
            elif t == "array":
                items = spec.get("items", {}) or {}
                if items.get("type") == "object":
                    fields.append(f"{name}[] {{ {render_props(items.get('properties', {}))} }}")
                else:
                    fields.append(f"{name}[]")
            elif t in _TYPE_HINT:
                fields.append(f"{name}({_TYPE_HINT[t]})")
            else:
                fields.append(name)
        return "  ".join(fields)

    return "{ " + render_props(schema.get("properties", {})) + " }"


class AgentQLExtractProvider:
    name = "agentql"

    def __init__(self, endpoint: str = AGENTQL_ENDPOINT) -> None:
        self._endpoint = endpoint
        self._key = os.environ.get("AGENTQL_API_KEY", "")

    def extract(self, source: str | WebResult, schema: dict[str, Any] | str,
                instruction: str = "") -> dict:
        import httpx

        query = schema if isinstance(schema, str) else json_schema_to_aql(schema)
        body: dict[str, Any] = {"query": query,
                                "params": {"mode": "standard", "wait_for": 0}}
        if isinstance(source, WebResult):
            if source.raw_html:
                body["html"] = source.raw_html
            else:
                body["url"] = source.url
        else:
            body["url"] = str(source)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(self._endpoint, json=body,
                                   headers={"X-API-Key": self._key,
                                            "Content-Type": "application/json"})
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
