import asyncio


def test_server_named_bad_research():
    from bad_research.mcp.server import server
    assert server.name == "bad-research"


def test_research_tools_registered():
    from bad_research.mcp.server import server
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    # inherited vault tools
    assert {"search_notes", "read_note", "fetch_url"} <= names
    # new research tools
    assert {"funnel_gather", "retrieve_chunks", "verify_citations", "route_query"} <= names
