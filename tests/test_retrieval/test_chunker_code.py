from bad_research.models.note import Note, NoteMeta
from bad_research.retrieval.chunker_code import (
    ast_header,
    chunk_code_note,
    embed_text_for,
)


def _code_note(body: str, source="https://github.com/o/r/blob/main/q.py") -> Note:
    meta = NoteMeta(title="q.py", id="qpy", source=source, content_type="code")
    return Note(meta=meta, body=body, path="research/qpy.md")


PY = (
    "def enqueue(x):\n"
    "    if x:\n"
    "        return clear(dequeue(x))\n"
    "    for i in range(3):\n"
    "        pass\n"
    "\n"
    "def helper():\n"
    "    return enqueue(1)\n"
)


def test_code_chunk_text_is_verbatim_body_slice():
    note = _code_note(PY)
    for c in chunk_code_note(note):
        assert c.text == note.body[c.char_start:c.char_end]


def test_ast_header_lists_calls_and_control_flow():
    h = ast_header("o/r/q.py", PY, language="python")
    assert h.splitlines()[0] == "o/r/q.py"
    # Calls present: clear, dequeue, range, enqueue appear as call_expressions.
    calls_line = next(line for line in h.splitlines() if line.startswith("Calls:"))
    assert "dequeue" in calls_line and "clear" in calls_line
    cf = next(line for line in h.splitlines() if line.startswith("Control flow:"))
    assert "branches" in cf and "loops" in cf and "complexity" in cf


def test_embed_text_prepends_header_then_blank_line_then_code():
    note = _code_note(PY)
    chunk = chunk_code_note(note)[0]
    et = embed_text_for(chunk, note)
    # Header, blank line, then the verbatim chunk text.
    assert et.startswith("o/r/q.py")
    assert "\n\n" in et
    assert et.endswith(chunk.text)


def test_non_call_file_omits_calls_line_but_keeps_path_and_controlflow():
    body = "X = 1\nY = 2\n"
    h = ast_header("o/r/c.py", body, language="python")
    lines = h.splitlines()
    assert lines[0] == "o/r/c.py"
    assert not any(line.startswith("Calls:") for line in lines)
    assert any(line.startswith("Control flow:") for line in lines)
