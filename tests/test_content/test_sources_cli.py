"""CLI-backed source tiers — yt-dlp/git/arxiv (dossier 12 §A/B/C). subprocess mocked."""

from __future__ import annotations

import pytest

import bad_research.web.content.sources as src
from bad_research.web.content.sources import (
    ExtractorUnavailable,
    _clean_vtt,
    arxiv_source_notes,
    github_clone_notes,
    youtube_transcript,
)


def test_clean_vtt_dedups_rolling(sample_vtt: str) -> None:
    # the rolling-caption VTT must collapse to the unique novel lines, no timing tags
    out = _clean_vtt(sample_vtt)
    assert "<c>" not in out and "-->" not in out and "WEBVTT" not in out
    assert "so today we're talking about caching" in out
    assert "the cache hit rate is forty percent" in out
    # the duplicated final cue appears once, not twice
    assert out.count("the cache hit rate is forty percent") == 1


def test_youtube_degrades_when_yt_dlp_absent(monkeypatch) -> None:
    monkeypatch.setattr(src.shutil, "which", lambda tool: None)   # yt-dlp not on PATH
    with pytest.raises(ExtractorUnavailable) as ei:
        youtube_transcript("https://youtu.be/abc")
    assert ei.value.tool == "yt-dlp"
    assert "yt-dlp" in ei.value.install_hint


def test_youtube_transcript_happy(monkeypatch, tmp_path, sample_vtt: str) -> None:
    monkeypatch.setattr(src.shutil, "which", lambda tool: "/usr/bin/yt-dlp")
    vtt_file = tmp_path / "vid.en.vtt"
    vtt_file.write_text(sample_vtt)

    def fake_run(cmd, **kw):
        return src.subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(src.subprocess, "run", fake_run)
    monkeypatch.setattr(src, "_ytdlp_subs_dir", lambda url: str(tmp_path))
    monkeypatch.setattr(src, "_ytdlp_json",
                        lambda url: {"title": "My Talk", "upload_date": "20240115"})
    note = youtube_transcript("https://youtu.be/abc")
    assert note["source_type"] == "youtube"
    assert note["title"] == "My Talk"
    assert note["published"].startswith("2024-01-15")
    assert "caching" in note["markdown"].lower()
    assert "yt-dlp" in note["provenance"]


def test_github_degrades_when_git_absent(monkeypatch) -> None:
    monkeypatch.setattr(src.shutil, "which", lambda tool: None)
    with pytest.raises(ExtractorUnavailable) as ei:
        github_clone_notes("https://github.com/owner/repo")
    assert ei.value.tool == "git"


def test_arxiv_source_notes(monkeypatch) -> None:
    import io
    import tarfile

    # build a tiny tarball with a .tex file, in-memory
    buf = io.BytesIO()
    tex = rb"\begin{document}\section{Intro}Hello arxiv body.\end{document}"
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("main.tex")
        info.size = len(tex)
        tar.addfile(info, io.BytesIO(tex))
    tarball = buf.getvalue()

    class _Resp:
        content = tarball

    monkeypatch.setattr(src.httpx, "get", lambda url, **kw: _Resp())
    monkeypatch.setattr(src, "assert_url_safe", lambda u: None)
    monkeypatch.setattr(src, "_arxiv_atom_meta",
                        lambda aid: {"title": "Intro Paper", "published": "2024-03-15"})
    note = arxiv_source_notes("https://arxiv.org/abs/2403.12345")
    assert note["source_type"] == "arxiv_src"
    assert note["title"] == "Intro Paper"
    assert "Intro" in note["markdown"]
    assert "Hello arxiv body" in note["markdown"]
