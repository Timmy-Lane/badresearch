from __future__ import annotations

from bad_research.funnel.filter import filter_and_store
from tests.test_funnel.conftest import FakeVault, FakeWebResult, fake_postfetch_filter


def _page(url, content, title=""):
    return FakeWebResult(url=url, title=title or url, content=content)


def test_drops_junk_via_postfetch_filter():
    pages = [
        _page("https://good.com/a", "real substantive content " * 40),
        _page("https://junk.com/b", "tiny"),          # < 300 chars -> junk
    ]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    assert len(stored) == 1                            # junk dropped


def test_drops_redundant_over_60pct_overlap():
    base = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 10
    pages = [
        _page("https://orig.com/a", base),
        _page("https://copy.com/b", base),             # identical → >60% overlap → drop
        _page("https://uniq.com/c", "completely orthogonal vocabulary here " * 20),
    ]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    assert len(stored) == 2                             # orig + uniq; copy discounted


def test_keeps_near_but_under_threshold():
    # ~33% overlap should NOT be dropped (only >60%). Bodies are long enough to
    # clear the 300-char junk gate so this exercises the redundancy threshold,
    # not the junk filter.
    a = "word_a " * 60 + "shared common phrase " * 5
    b = "word_b " * 60 + "shared common phrase " * 5
    pages = [_page("https://a.com/a", a), _page("https://b.com/b", b)]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    assert len(stored) == 2


def test_stores_raw_body_to_vault_returns_note_ids():
    pages = [_page("https://good.com/a", "substantive content body " * 40)]
    vault = FakeVault()
    stored = filter_and_store(pages, vault=vault, postfetch_filter=fake_postfetch_filter,
                              redundancy_overlap=0.60, shingle_n=3)
    note_id, body = stored[0]
    assert note_id in vault.notes                       # the raw body lives on disk
    assert "substantive content" in vault.notes[note_id]
    assert "substantive content" in body                # passed to RetrievalEngine.index


def test_empty_input_returns_empty():
    assert filter_and_store([], vault=FakeVault(), postfetch_filter=fake_postfetch_filter,
                            redundancy_overlap=0.60, shingle_n=3) == []
