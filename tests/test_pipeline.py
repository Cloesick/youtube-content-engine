"""Offline tests — exercise the pipeline logic with NO network and NO API keys.

Covers the pure/critical pieces: ranking scraped videos, JSON parsing of LLM
output (incl. markdown fences), dedupe-key determinism, list splitting, the
full generate orchestration (with mocked YouTube/Gemini/Airtable), and clip
rendering. Run: .venv\\Scripts\\python -m pytest -q
"""
from __future__ import annotations

import os
import sys

# Importing the package must not require any env vars.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yt_content.airtable import Channel, _split_list
from yt_content.config import Settings
from yt_content.generate import Idea, _extract_json, _inspiration_digest
from yt_content.repurpose import Clip
from yt_content.youtube import summarize_inspiration


# ---------- youtube.summarize_inspiration ----------

def _vid(vid, title, views, comments=0):
    return {
        "id": vid,
        "snippet": {"title": title, "channelTitle": "Chan", "publishedAt": "2026-01-02T00:00:00Z", "description": "d"},
        "statistics": {"viewCount": str(views), "commentCount": str(comments)},
    }


def test_summarize_ranks_by_engagement_and_trims():
    raw = [_vid("a", "Low", 100), _vid("b", "High", 100000), _vid("c", "", 999)]
    out = summarize_inspiration(raw, top_n=2)
    assert len(out) == 2                      # empty-title row dropped, trimmed to 2
    assert out[0]["title"] == "High"          # ranked by views/engagement
    assert out[0]["url"] == "https://youtu.be/b"
    assert out[0]["views"] == 100000


def test_summarize_handles_missing_stats():
    raw = [{"id": "x", "snippet": {"title": "T"}, "statistics": {}}]
    out = summarize_inspiration(raw)
    assert out[0]["views"] == 0 and out[0]["comments"] == 0


# ---------- generate._extract_json ----------

def test_extract_json_plain():
    assert _extract_json('[{"title":"x"}]') == [{"title": "x"}]


def test_extract_json_with_markdown_fence():
    text = '```json\n[{"title":"x"}]\n```'
    assert _extract_json(text) == [{"title": "x"}]


def test_extract_json_with_surrounding_prose():
    text = 'Here you go:\n[{"title":"x"}]\nHope that helps!'
    assert _extract_json(text) == [{"title": "x"}]


# ---------- dedupe key ----------

def test_dedupe_key_stable_and_channel_scoped():
    idea = Idea("My Title", "h", "s", "t", ["a"], "w")
    k1 = idea.dedupe_key("ChanA")
    k2 = idea.dedupe_key("ChanA")
    k3 = idea.dedupe_key("ChanB")
    assert k1 == k2 and k1 != k3 and len(k1) == 16


def test_dedupe_key_ignores_case_and_whitespace():
    a = Idea("Hello   World", "", "", "", [], "").dedupe_key("C")
    b = Idea("hello world", "", "", "", [], "").dedupe_key("C")
    assert a == b


# ---------- airtable._split_list ----------

def test_split_list_variants():
    assert _split_list("a, b\nc") == ["a", "b", "c"]
    assert _split_list(["x", " y "]) == ["x", "y"]
    assert _split_list(None) == []


# ---------- repurpose.Clip.render ----------

def test_clip_render():
    c = Clip("hook", "script", "cap", ["one", "two"])
    r = c.render(1)
    assert "CLIP 1" in r and "#one #two" in r and "HOOK: hook" in r


# ---------- full generate orchestration (mocked I/O) ----------

def test_generate_for_channel_builds_records_and_dedupes(monkeypatch):
    from yt_content import main as m

    settings = Settings.load()  # no keys needed; we mock the clients
    object.__setattr__(settings, "ideas_per_channel", 2)

    ch = Channel(
        record_id="rec1", name="Web Dev / Tech", niche="web dev",
        keywords=["react"], competitor_channels=[], tone="energetic",
        active=True, ideas_per_run=2, cta=None, lead_magnet=None, region=None,
    )

    class FakeYT:
        def scrape_keywords(self, kw, region=None):
            return [_vid("a", "Top React Video", 50000, 10)]

    class FakeGen:
        def generate(self, channel, inspiration, count):
            assert inspiration and inspiration[0]["title"] == "Top React Video"
            return [
                Idea("Idea One", "h1", "s1", "t1", ["x"], "w1"),
                Idea("Idea One", "h1", "s1", "t1", ["x"], "w1"),  # dup -> filtered
                Idea("Idea Two", "h2", "s2", "t2", ["y"], "w2"),
            ]

    captured = {}

    class FakeAir:
        def existing_dedupe_keys(self, name):
            return set()
        def create_ideas(self, records):
            captured["records"] = records
            return len(records)

    created = m._generate_for_channel(settings, FakeAir(), FakeYT(), FakeGen(), ch)

    assert created == 2  # 3 ideas, 1 was a duplicate
    titles = [r["Title"] for r in captured["records"]]
    assert titles == ["Idea One", "Idea Two"]
    r0 = captured["records"][0]
    assert r0["Channel"] == "Web Dev / Tech"
    assert r0["Status"] == "Idea"
    assert r0["Tags"] == "x"
    assert "Top React Video" in r0["Source Insights"]
    assert len(r0["Dedupe Key"]) == 16


def test_generate_dry_run_writes_nothing(monkeypatch):
    from yt_content import main as m

    settings = Settings.load()
    object.__setattr__(settings, "dry_run", True)

    ch = Channel("rec", "C", "n", ["k"], [], "t", True, 1, None, None, None)

    class FakeYT:
        def scrape_keywords(self, kw, region=None):
            return []

    class FakeGen:
        def generate(self, channel, inspiration, count):
            return [Idea("T", "h", "s", "th", ["a"], "w")]

    class FakeAir:
        def existing_dedupe_keys(self, name):
            return set()
        def create_ideas(self, records):
            raise AssertionError("dry-run must not write to Airtable")

    created = m._generate_for_channel(settings, FakeAir(), FakeYT(), FakeGen(), ch)
    assert created == 0
