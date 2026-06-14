"""Orchestrator.

Usage:
  python -m yt_content.main generate    # scrape competitors + write video ideas to Airtable
  python -m yt_content.main repurpose   # turn your long-form transcripts into short-form clips
  python -m yt_content.main all         # both (default)

Scales by data: it loops over every Active row in the YT Channels table, so going
from 1 channel to 20 is adding rows, not code.

There is intentionally no auto-publish phase: uploading to YouTube needs OAuth and
real video files you film/edit. This engine fills your idea + clip pipeline; you
film, edit, and upload.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from .airtable import AirtableClient, Channel
from .config import Settings
from .generate import IdeaGenerator, _inspiration_digest
from .youtube import YouTubeClient, summarize_inspiration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("yt_content")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_generate(settings: Settings) -> int:
    air = AirtableClient(settings)
    yt = YouTubeClient(settings)
    generator = IdeaGenerator(settings)

    channels = air.get_active_channels()
    log.info("Found %d active channel(s)", len(channels))
    total_created = 0

    for ch in channels:
        try:
            total_created += _generate_for_channel(settings, air, yt, generator, ch)
        except Exception:  # one bad channel must not kill the fleet run
            log.exception("Generation failed for channel %s", ch.name)

    log.info("Done. Created %d new idea(s) total.", total_created)
    return total_created


def _generate_for_channel(
    settings: Settings,
    air: AirtableClient,
    yt: YouTubeClient,
    generator: IdeaGenerator,
    ch: Channel,
) -> int:
    if not ch.keywords:
        log.warning("Channel %s has no keywords — skipping", ch.name)
        return 0

    count = ch.ideas_per_run or settings.ideas_per_channel
    raw = yt.scrape_keywords(ch.keywords, region=ch.region)
    inspiration = summarize_inspiration(raw)
    source_digest = _inspiration_digest(inspiration)

    ideas = generator.generate(ch, inspiration, count)
    if not ideas:
        log.warning("No ideas generated for %s", ch.name)
        return 0

    seen = air.existing_dedupe_keys(ch.name)
    records = []
    for idea in ideas:
        key = idea.dedupe_key(ch.name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "Title": idea.title,
                "Channel": ch.name,
                "Status": "Idea",
                "Hook": idea.hook,
                "Script": idea.script,
                "Thumbnail Concept": idea.thumbnail_concept,
                "Tags": ", ".join(idea.tags),
                "Why It Works": idea.why_it_works,
                "Source Insights": source_digest,
                "Dedupe Key": key,
                "Created At": _now_iso(),
            }
        )

    if not records:
        log.info("All %d ideas for %s were duplicates — nothing new", len(ideas), ch.name)
        return 0

    if settings.dry_run:
        log.info("[DRY-RUN] Would create %d idea(s) for %s:", len(records), ch.name)
        for r in records:
            log.info("  • %s", r["Title"])
        return 0

    created = air.create_ideas(records)
    log.info("Created %d idea(s) for %s", created, ch.name)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube content engine")
    parser.add_argument(
        "phase",
        nargs="?",
        default="all",
        choices=["generate", "repurpose", "all"],
        help="Which phase to run (default: all)",
    )
    args = parser.parse_args(argv)

    settings = Settings.load()

    if args.phase in ("generate", "all"):
        run_generate(settings)
    if args.phase in ("repurpose", "all"):
        from .repurpose import run_repurpose

        run_repurpose(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
