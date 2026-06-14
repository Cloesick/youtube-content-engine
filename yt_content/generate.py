"""Video idea generation with Gemini.

Feeds the scraped top-performing videos as *inspiration* (proven titles, hooks,
formats) and asks for ORIGINAL video concepts — titles, hooks, scripts, and
thumbnail ideas — never copies and never suggests re-uploading others' footage.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from .airtable import Channel
from .config import Settings

log = logging.getLogger("yt_content.generate")


@dataclass
class Idea:
    title: str
    hook: str
    script: str
    thumbnail_concept: str
    tags: list[str]
    why_it_works: str

    def dedupe_key(self, channel_name: str) -> str:
        norm = re.sub(r"\s+", " ", self.title.lower()).strip()
        return hashlib.sha1(f"{channel_name}|{norm}".encode()).hexdigest()[:16]


_PROMPT = """You are a senior YouTube strategist and scriptwriter for a channel in \
the "{niche}" niche. Brand voice: {tone}.

Below are {n} of the TOP-PERFORMING videos in this niche right now, pulled from \
YouTube and ranked by views/engagement. Study their title patterns, angles, and \
what drives the click. Do NOT copy them and NEVER suggest re-uploading or reusing \
their footage — produce ORIGINAL video concepts the creator will film themselves.

TOP-PERFORMING INSPIRATION:
{inspiration}
{cta_block}
Design {count} original YouTube videos for this channel. For each, return:
- "title": a click-worthy, honest title (<= 70 chars, no clickbait lies)
- "hook": the first 5-10 seconds of spoken script that stops the scroll
- "script": a tight outline/script the creator can film from (intro, 3-5 beats, payoff, CTA)
- "thumbnail_concept": thumbnail text (3-5 words) + the visual
- "tags": 8-12 relevant YouTube search tags (no leading #)
- "why_it_works": one or two sentences on the proven pattern this borrows and why it should perform

Lead with genuine value the viewer actually gets. Keep titles truthful — no fake \
claims, no deceptive thumbnails. The title earns the click; the video delivers.

Return ONLY a JSON array of objects with keys title, hook, script, thumbnail_concept, \
tags, why_it_works. No markdown, no commentary."""


def _cta_block(channel: Channel) -> str:
    if channel.cta:
        return f"\nCALL TO ACTION: End each script with this CTA: {channel.cta!r}\n"
    if channel.lead_magnet:
        return (
            f"\nCALL TO ACTION: End each script with a soft, honest CTA inviting the "
            f"viewer to grab the free '{channel.lead_magnet}' (link in description / "
            f"end screen).\n"
        )
    return ""


def _format_inspiration(items: list[dict]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. [{it['views']:,} views, {it['comments']:,} comments] "
            f"\"{it['title']}\" — {it['channel']} ({it['published']})"
        )
    return (
        "\n".join(lines)
        if lines
        else "(no scrape data available — use niche best practices)"
    )


def _inspiration_digest(items: list[dict], top_n: int = 6) -> str:
    """Compact source list stored on each idea row for traceability."""
    lines = [
        f"• {it['title']} — {it['channel']} ({it['views']:,} views) {it['url']}"
        for it in items[:top_n]
    ]
    return "\n".join(lines)


def _extract_json(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


class IdeaGenerator:
    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        import google.generativeai as genai  # local import: non-generate runs don't need it

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(settings.gemini_model)

    def generate(
        self, channel: Channel, inspiration: list[dict], count: int
    ) -> list[Idea]:
        prompt = _PROMPT.format(
            niche=channel.niche or "general",
            tone=channel.tone or "friendly, expert",
            n=len(inspiration),
            inspiration=_format_inspiration(inspiration),
            cta_block=_cta_block(channel),
            count=count,
        )
        resp = self._model.generate_content(prompt)
        try:
            data = _extract_json(resp.text)
        except (json.JSONDecodeError, ValueError) as e:
            log.error("Could not parse Gemini output for %s: %s", channel.name, e)
            return []

        ideas: list[Idea] = []
        for obj in data:
            if not isinstance(obj, dict) or not obj.get("title"):
                continue
            tags = obj.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
            ideas.append(
                Idea(
                    title=str(obj["title"]).strip(),
                    hook=str(obj.get("hook", "")).strip(),
                    script=str(obj.get("script", "")).strip(),
                    thumbnail_concept=str(obj.get("thumbnail_concept", "")).strip(),
                    tags=[str(t).lstrip("#") for t in tags][:12],
                    why_it_works=str(obj.get("why_it_works", "")).strip(),
                )
            )
        return ideas
