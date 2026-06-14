"""Phase 2 — the clip / repurpose engine.

Takes YOUR own long-form videos (a row in the `YT Clips` table with a pasted
transcript or notes) and asks Gemini to cut them into short-form concepts —
Shorts / Reels / TikTok hooks, 30-45s scripts, captions, and hashtags.

It only works from material you provide for content you own (see COMPLIANCE.md).
No OAuth, no downloading anyone's footage — just turns your transcript into a
clip plan you edit and post.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass

from .airtable import AirtableClient
from .config import Settings

log = logging.getLogger("yt_content.repurpose")


@dataclass
class Clip:
    hook: str
    script: str
    caption: str
    hashtags: list[str]

    def render(self, index: int) -> str:
        tags = " ".join(f"#{h}" for h in self.hashtags)
        return (
            f"--- CLIP {index} ---\n"
            f"HOOK: {self.hook}\n"
            f"SCRIPT: {self.script}\n"
            f"CAPTION: {self.caption}\n"
            f"HASHTAGS: {tags}"
        )


_PROMPT = """You are a short-form video editor for a "{niche}" YouTube channel. \
Brand voice: {tone}.

Below is the transcript/notes of a LONG-FORM video the creator already made and \
owns. Find the {count} most clip-worthy moments and turn each into a self-contained \
short (YouTube Shorts / Reels / TikTok, ~30-45 seconds).

SOURCE VIDEO: {source_title}

TRANSCRIPT / NOTES:
{transcript}

For each clip return:
- "hook": a punchy first line (first 2 seconds) that stops the scroll
- "script": the ~30-45s spoken script for the clip, drawn from the source material
- "caption": a short caption for the post
- "hashtags": 5-8 relevant hashtags (no leading #)

Pick moments that stand alone without the full context. Keep it truthful to the \
source. Return ONLY a JSON array of objects with keys hook, script, caption, \
hashtags. No markdown, no commentary."""


def _extract_json(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


class ClipGenerator:
    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(settings.gemini_model)

    def generate(
        self,
        *,
        niche: str,
        tone: str,
        source_title: str,
        transcript: str,
        count: int,
    ) -> list[Clip]:
        prompt = _PROMPT.format(
            niche=niche or "general",
            tone=tone or "energetic, clear",
            count=count,
            source_title=source_title or "(untitled)",
            transcript=transcript[:12000],  # keep the prompt bounded
        )
        resp = self._model.generate_content(prompt)
        try:
            data = _extract_json(resp.text)
        except (json.JSONDecodeError, ValueError) as e:
            log.error("Could not parse Gemini clip output for %r: %s", source_title, e)
            return []

        clips: list[Clip] = []
        for obj in data:
            if not isinstance(obj, dict) or not obj.get("hook"):
                continue
            hashtags = obj.get("hashtags") or []
            if isinstance(hashtags, str):
                hashtags = [h.strip().lstrip("#") for h in hashtags.split() if h.strip()]
            clips.append(
                Clip(
                    hook=str(obj.get("hook", "")).strip(),
                    script=str(obj.get("script", "")).strip(),
                    caption=str(obj.get("caption", "")).strip(),
                    hashtags=[str(h).lstrip("#") for h in hashtags][:8],
                )
            )
        return clips


def _channel_voice(air: AirtableClient, channel_name: str) -> tuple[str, str]:
    """Look up niche/tone from YT Channels so clips match the brand voice."""
    for ch in air.get_active_channels():
        if ch.name == channel_name:
            return ch.niche, ch.tone
    return "", ""


def run_repurpose(settings: Settings) -> int:
    air = AirtableClient(settings)
    gen = ClipGenerator(settings)

    # Rows that have source material but haven't been processed yet.
    rows = air._list(
        settings.clips_table,
        params={"filterByFormula": "OR({Status} = 'New', {Status} = '')"},
    )
    log.info("Found %d clip source(s) to process", len(rows))

    processed = 0
    for row in rows:
        f = row.get("fields", {})
        transcript = str(f.get("Transcript / Notes", "")).strip()
        source_title = str(f.get("Source Title", "")).strip()
        channel = str(f.get("Channel", "")).strip()
        if not transcript:
            log.info("Skipping %r — no transcript/notes yet", source_title or row["id"])
            continue

        count = (
            int(f["Clips Wanted"])
            if f.get("Clips Wanted") not in (None, "")
            else settings.clips_per_source
        )
        niche, tone = _channel_voice(air, channel)

        clips = gen.generate(
            niche=niche,
            tone=tone,
            source_title=source_title,
            transcript=transcript,
            count=count,
        )
        if not clips:
            log.warning("No clips generated for %r", source_title)
            continue

        rendered = "\n\n".join(c.render(i) for i, c in enumerate(clips, 1))
        dedupe = hashlib.sha1(
            f"{source_title}|{len(transcript)}".encode()
        ).hexdigest()[:16]

        if settings.dry_run:
            log.info("[DRY-RUN] %d clip(s) for %r:\n%s", len(clips), source_title, rendered)
            continue

        air.update_record(
            settings.clips_table,
            row["id"],
            {"Generated Clips": rendered, "Status": "Generated", "Dedupe Key": dedupe},
        )
        log.info("Generated %d clip(s) for %r", len(clips), source_title)
        processed += 1

    log.info("Repurpose done. Processed %d source(s).", processed)
    return processed
