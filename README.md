# YouTube Content Engine

A research/ideation pipeline that uses **Airtable as the control plane** to turn
*what's already winning on YouTube* into **your own original video ideas, hooks,
scripts, and thumbnail concepts** — ready to film.

It mirrors the `InstagramContentEngine` architecture:

```
YouTube Data API (scrape)  ->  Gemini (generate)  ->  Airtable (queue you film from)
```

Airtable doesn't scrape anything itself — it's the brain: it stores your channel
config and holds the idea pipeline with a status lifecycle. The YouTube Data API
does the scraping; Gemini does the thinking.

## What it does

For every **Active** channel row in Airtable, each run:

1. Searches the YouTube Data API for your `Keywords`, ranked by **view count**.
2. Enriches the top videos with stats (views / likes / comments).
3. Feeds those proven performers to Gemini as *inspiration*.
4. Gets back N **original** video concepts — title, hook, full script outline,
   thumbnail concept, tags, and *why it works*.
5. De-dupes against what's already in the queue and writes new rows as `Idea`.

You then move rows `Idea → Scripted → Filmed → Published` as you work.

> **It never copies or re-uploads anyone's footage.** It studies public metadata
> to produce original content you create. See `COMPLIANCE.md`.

## Airtable base

Base: **YouTube Content Engine** (`app4nnEYqZaKjBo1h`)

**`YT Channels`** — one row per channel/niche (config):

| Field | Purpose |
|---|---|
| Name | Your channel name (matches `Channel` in the queue) |
| Niche | What the channel is about |
| Keywords | Comma/newline-separated search terms to research |
| Competitor Channels | Optional handles/IDs to focus on |
| Tone | Brand voice |
| Active | ✅ = processed by the engine |
| Ideas Per Run | Override default ideas generated per run |
| CTA | Optional explicit call-to-action for scripts |
| Lead Magnet | Free resource the end-screen CTA points to |
| Region | Optional ISO region code (e.g. `BE`) |

**`YT Content Queue`** — generated ideas, lifecycle `Idea → Scripted → Filmed → Published / Archived`:
Title, Hook, Script, Thumbnail Concept, Tags, Why It Works, Source Insights, Dedupe Key, Created At.

**`YT Clips`** (phase 2 — repurpose engine) — one row per **your own** long-form video.
Paste its transcript/notes; the `repurpose` phase generates short-form (Shorts/Reels/TikTok)
clip concepts (hook + ~30-45s script + caption + hashtags). Lifecycle `New → Generated → Edited → Posted`.

## Setup

1. **Keys** (see `.env.example`):
   - `AIRTABLE_TOKEN` — Airtable PAT with read/write on the base.
   - `YT_AIRTABLE_BASE_ID` — already `app4nnEYqZaKjBo1h`.
   - `YOUTUBE_API_KEY` — Google Cloud key with **YouTube Data API v3** enabled
     (free quota ≈ 10,000 units/day ≈ 100 searches).
   - `GEMINI_API_KEY` — your existing Google AI Studio key.

2. **Add a channel row** in `YT Channels`, set `Active` ✅ and a few `Keywords`.

3. **Run locally** (safe dry-run first):

   ```bash
   pip install -r requirements.txt
   cp .env.example .env   # fill in keys
   # PowerShell: setx in your shell, or use a .env loader. Then:
   YT_DRY_RUN=true python -m yt_content.main generate   # logs ideas, writes nothing
   python -m yt_content.main generate                   # writes ideas to Airtable
   python -m yt_content.main repurpose                  # transcripts in YT Clips -> short-form concepts
   python -m yt_content.main all                        # both phases
   ```

4. **Automate** with GitHub Actions: push this repo, add the four keys as repo
   **Secrets** (`AIRTABLE_TOKEN`, `YT_AIRTABLE_BASE_ID`, `YOUTUBE_API_KEY`,
   `GEMINI_API_KEY`). The workflow runs daily at 07:15 UTC, or trigger it
   manually via **Run workflow** (with an optional dry-run toggle).

## Cost / quota

- **YouTube Data API**: `search.list` = 100 units, `videos.list` ≈ 1 unit. One
  channel with ~3 keywords ≈ ~300 units/run. The free 10k/day quota covers many
  channels run daily.
- **Gemini**: one prompt per channel per run on `gemini-2.0-flash` (cheap).

## Scaling

Add channels by adding rows. Going from 1 channel to 20 is data, not code —
exactly like the Instagram engine.

## Roadmap

- ✅ `repurpose` phase: turns your own long-form transcripts into Shorts/Reels/TikTok
  clip concepts (the "clip engine") — in the `YT Clips` table.
- Optional auto-upload via the YouTube Data API (needs OAuth + rendered files).
- Optional transcript auto-fetch for your own videos (needs OAuth captions scope).
