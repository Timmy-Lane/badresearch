"""AgentQL (AQL) query language — keyless port + host-model resolver.

The parser is ported VERBATIM from the installed agentql==1.18.1 SDK
(_core/_syntax/{lexer,parser,node,token_kind}.py), reconstructed in
products/AGENTQL_PRODUCT_CODE.md:1249-1631 and documented in dossier 14 §6.1.

Grammar (EBNF, KNOWN — AGENTQL_PRODUCT_CODE.md:1240-1247):
    Query       ::= '{' NodeList '}'
    NodeList    ::= Node ((',' | NEWLINE) Node)*
    Node        ::= IDENTIFIER Description? (Container | List | epsilon)
    Description ::= '(' DescContent ')'
    DescContent ::= (Letter | Digit | Symbol | WS | '(' DescContent ')')*
    Container   ::= '{' NodeList '}'
    List        ::= '[]' Container?
    IDENTIFIER  ::= [a-zA-Z_][a-zA-Z0-9_]*

The AQL string IS the wire format (no separate serializer); Node.dump() round-trips.
There is NO paid LLM call here — the resolver (AqlExtractProvider, below) uses the
host-model LLMProvider seam by injection, or falls back to deterministic name-matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================ Token Types
class TokenKind(Enum):
    SOF = "SOF"
    EOF = "EOF"
    BRACE_L = "{"
    BRACE_R = "}"
    BRACKET_L = "["
    BRACKET_R = "]"
    PAREN_L = "("
    PAREN_R = ")"
    COMMA = ","
    NEWLINE = "NEWLINE"
    IDENTIFIER = "IDENTIFIER"
    DESCRIPTION = "DESCRIPTION"


IGNORED_TOKENS = {TokenKind.NEWLINE}


@dataclass
class Token:
    kind: TokenKind
    value: str
    line: int
    column: int
    prev: Optional["Token"] = None
    next: Optional["Token"] = None


# ============================================================ AST Node Types
@dataclass
class Node:
    name: str
    description: Optional[str] = None

    def get_child_by_name(self, name: str) -> Optional["Node"]:
        return None


@dataclass
class IdNode(Node):
    """Single element: `search_btn` or `search_btn(the main one)`."""


@dataclass
class IdListNode(Node):
    """List of elements: `links[]`."""


@dataclass
class ContainerNode(Node):
    """Scoped container: `nav { home_link about_link }` or the root query."""

    children: list[Node] = field(default_factory=list)

    def get_child_by_name(self, name: str) -> Optional[Node]:
        for child in self.children:
            if child.name == name:
                return child
        return None


@dataclass
class ContainerListNode(Node):
    """List of structured objects: `products[] { name price }`."""

    children: list[Node] = field(default_factory=list)

    def get_child_by_name(self, name: str) -> Optional[Node]:
        for child in self.children:
            if child.name == name:
                return child
        return None


# ============================================================ Errors
class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int) -> None:
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


class QuerySyntaxError(Exception):
    def __init__(self, message: str, line: int = 0, column: int = 0) -> None:
        self.code = 1010
        self.line = line
        self.column = column
        super().__init__(f"1010 QuerySyntaxError: {message} on row {line}")


# ============================================================ Lexer
class Lexer:
    """Character-by-character tokenizer producing a linked list of Token objects."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.head: Optional[Token] = None
        self.tail: Optional[Token] = None

    def tokenize(self) -> Token:
        sof = Token(TokenKind.SOF, "", 1, 0)
        self.head = sof
        self.tail = sof
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in (" ", "\t"):
                self.pos += 1
                self.column += 1
                continue
            if ch in ("\r", "\n"):
                if ch == "\r" and self._peek(1) == "\n":
                    self.pos += 1
                self._emit(TokenKind.NEWLINE, ch)
                self.pos += 1
                self.line += 1
                self.column = 1
                continue
            if ch == "{":
                self._emit(TokenKind.BRACE_L, ch)
            elif ch == "}":
                self._emit(TokenKind.BRACE_R, ch)
            elif ch == "[":
                self._emit(TokenKind.BRACKET_L, ch)
            elif ch == "]":
                self._emit(TokenKind.BRACKET_R, ch)
            elif ch == ",":
                self._emit(TokenKind.COMMA, ch)
            elif ch == "(":
                self._scan_description()
                continue
            elif ch.isalpha() or ch == "_":
                self._scan_identifier()
                continue
            else:
                raise LexerError(f"Unexpected character '{ch}'", self.line, self.column)
            self.pos += 1
            self.column += 1
        self._emit(TokenKind.EOF, "")
        return self.head

    def _emit(self, kind: TokenKind, value: str) -> None:
        token = Token(kind, value, self.line, self.column)
        token.prev = self.tail
        self.tail.next = token
        self.tail = token

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _scan_identifier(self) -> None:
        start = self.pos
        start_col = self.column
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch.isalnum() or ch == "_":
                self.pos += 1
                self.column += 1
            else:
                break
        value = self.source[start : self.pos]
        token = Token(TokenKind.IDENTIFIER, value, self.line, start_col)
        token.prev = self.tail
        self.tail.next = token
        self.tail = token

    def _scan_description(self) -> None:
        """Scan from ( to matching ), handling nested parens."""
        start_line = self.line
        start_col = self.column
        self.pos += 1
        self.column += 1
        depth = 1
        content: list[str] = []
        while self.pos < len(self.source) and depth > 0:
            ch = self.source[self.pos]
            if ch == "(":
                depth += 1
                content.append(ch)
            elif ch == ")":
                depth -= 1
                if depth > 0:
                    content.append(ch)
            elif ch == "\n":
                content.append(ch)
                self.line += 1
                self.column = 0
            else:
                content.append(ch)
            self.pos += 1
            self.column += 1
        if depth != 0:
            raise LexerError("Unclosed description parenthesis", start_line, start_col)
        desc_text = "".join(content).strip()
        if len(desc_text) >= 2 and (
            (desc_text[0] == '"' and desc_text[-1] == '"')
            or (desc_text[0] == "'" and desc_text[-1] == "'")
        ):
            desc_text = desc_text[1:-1].strip()
        self._emit(TokenKind.DESCRIPTION, desc_text)


# ============================================================ Recursive-Descent Parser
class QueryParser:
    """Parses AgentQL query strings into an AST (root ContainerNode)."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.lexer = Lexer(query)
        self.current: Optional[Token] = None

    def parse(self) -> ContainerNode:
        sof = self.lexer.tokenize()
        self.current = sof.next  # skip SOF
        self._skip_ignored()
        self._expect(TokenKind.BRACE_L)
        self._advance()
        children = self._parse_node_list()
        self._expect(TokenKind.BRACE_R)
        self._advance()
        self._skip_ignored()
        if self.current and self.current.kind != TokenKind.EOF:
            raise QuerySyntaxError(
                f"Expected end of query, found {self.current.kind.value}",
                self.current.line,
                self.current.column,
            )
        return ContainerNode(name="", children=children)

    def _parse_node_list(self) -> list[Node]:
        nodes: list[Node] = []
        seen_names: set[str] = set()
        while True:
            self._skip_ignored()
            if not self.current or self.current.kind in (TokenKind.BRACE_R, TokenKind.EOF):
                break
            node = self._parse_node()
            if node.name in seen_names:
                raise QuerySyntaxError(
                    f"Duplicate identifier '{node.name}'",
                    self.current.line if self.current else 0,
                    self.current.column if self.current else 0,
                )
            seen_names.add(node.name)
            nodes.append(node)
            self._skip_ignored()
            if self.current and self.current.kind == TokenKind.COMMA:
                self._advance()
        return nodes

    def _parse_node(self) -> Node:
        """Parse: IDENTIFIER Description? (Container | List | epsilon)."""
        self._skip_ignored()
        self._expect(TokenKind.IDENTIFIER)
        name = self.current.value
        self._advance()
        description = None
        self._skip_ignored()
        if self.current and self.current.kind == TokenKind.DESCRIPTION:
            description = self.current.value
            self._advance()
        self._skip_ignored()
        is_list = False
        if self.current and self.current.kind == TokenKind.BRACKET_L:
            self._advance()
            self._expect(TokenKind.BRACKET_R)
            self._advance()
            is_list = True
        self._skip_ignored()
        if self.current and self.current.kind == TokenKind.BRACE_L:
            self._advance()
            children = self._parse_node_list()
            self._expect(TokenKind.BRACE_R)
            self._advance()
            if is_list:
                return ContainerListNode(name=name, description=description, children=children)
            return ContainerNode(name=name, description=description, children=children)
        if is_list:
            return IdListNode(name=name, description=description)
        return IdNode(name=name, description=description)

    def _advance(self) -> None:
        if self.current and self.current.next:
            self.current = self.current.next
        self._skip_ignored()

    def _skip_ignored(self) -> None:
        while self.current and self.current.kind in IGNORED_TOKENS:
            self.current = self.current.next

    def _expect(self, kind: TokenKind) -> None:
        if not self.current or self.current.kind != kind:
            found = self.current.kind.value if self.current else "EOF"
            raise QuerySyntaxError(
                f"Expected {kind.value}, found {found}",
                self.current.line if self.current else 0,
                self.current.column if self.current else 0,
            )


def parse_aql(query: str) -> ContainerNode:
    """Public entry: validate + parse an AQL string into its root ContainerNode AST."""
    return QueryParser(query).parse()
