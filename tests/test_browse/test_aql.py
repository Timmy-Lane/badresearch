"""The ported AgentQL AQL parser — full grammar coverage. Pure Python, no mocks needed."""

from __future__ import annotations

import pytest

from bad_research.browse.aql import (
    ContainerListNode,
    ContainerNode,
    IdListNode,
    IdNode,
    QuerySyntaxError,
    parse_aql,
)


def test_two_flat_elements() -> None:
    ast = parse_aql("{ search_box  search_button }")
    assert isinstance(ast, ContainerNode)
    assert ast.name == ""
    assert [c.name for c in ast.children] == ["search_box", "search_button"]
    assert all(isinstance(c, IdNode) for c in ast.children)


def test_id_list_node() -> None:
    ast = parse_aql("{ links[] }")
    assert len(ast.children) == 1
    node = ast.children[0]
    assert isinstance(node, IdListNode)
    assert node.name == "links"


def test_container_list_of_objects() -> None:
    ast = parse_aql("{ products[] { name  price  rating } }")
    products = ast.children[0]
    assert isinstance(products, ContainerListNode)
    assert products.name == "products"
    assert [c.name for c in products.children] == ["name", "price", "rating"]
    assert all(isinstance(c, IdNode) for c in products.children)


def test_nested_container() -> None:
    ast = parse_aql("{ login_form { username_input  password_input  submit_button } }")
    form = ast.children[0]
    assert isinstance(form, ContainerNode)
    assert form.get_child_by_name("submit_button") is not None
    assert form.get_child_by_name("missing") is None


def test_description_parens_with_nesting() -> None:
    ast = parse_aql("{ price(sale price (not list price)) }")
    node = ast.children[0]
    assert isinstance(node, IdNode)
    assert node.name == "price"
    assert node.description == "sale price (not list price)"


def test_mixed_list_and_container() -> None:
    ast = parse_aql("{ nav_links[]  footer { copyright  privacy_link } }")
    assert isinstance(ast.children[0], IdListNode)
    assert isinstance(ast.children[1], ContainerNode)


def test_comma_separator_optional() -> None:
    # comma between siblings is legal but optional
    a = parse_aql("{ a, b, c }")
    b = parse_aql("{ a b c }")
    assert [n.name for n in a.children] == [n.name for n in b.children] == ["a", "b", "c"]


def test_newline_separator() -> None:
    ast = parse_aql("{\n  a\n  b\n}")
    assert [n.name for n in ast.children] == ["a", "b"]


def test_no_reserved_words() -> None:
    # query/select/from/true/null are all legal identifiers
    ast = parse_aql("{ query  select  from  true  null }")
    assert [n.name for n in ast.children] == ["query", "select", "from", "true", "null"]


def test_duplicate_identifier_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a  a }")


def test_missing_opening_brace_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("search_box")


def test_unclosed_brace_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a ")


def test_trailing_garbage_rejected() -> None:
    with pytest.raises(QuerySyntaxError):
        parse_aql("{ a } extra")


def test_quotes_stripped_from_description() -> None:
    ast = parse_aql('{ x("the blue one") }')
    assert ast.children[0].description == "the blue one"
