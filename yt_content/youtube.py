"""YouTube Data API client — the scrape layer.

Searches the public YouTube Data API v3 for top videos matching a channel's
keywords, then enriches them with statistics (views/likes/comments). These
top-performers feed the idea generator as *inspiration* — we study what works
and produce original content, never copy or re-upload.

Quota note: search.list costs 100 units; videos.list costs ~1 unit. The default
free quota is 10,000 units/day (~100 searches), which is plenty for a daily
cron over a handful of channels.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import Settings
from .http import make_session

log = logging.getLogger("yt_content.youtube")

API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeClient:
    def __init__(self, settings: Settings):
        if not settings.youtube_api_key:
            raise RuntimeError("YOUTUBE_API_KEY is not set.")
        self.s = settings
        self.session = make_session()

    def _search_ids(self, keyword: str, region: str | None) -> list[str]:
        """search.list ordered by viewCount -> candidate video IDs."""
        params = {
            "key": self.s.youtube_api_key,
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "maxResults": min(self.s.search_results_per_keyword, 50),
        }
        if region:
            params["regionCode"] = region
        resp = self.session.get(f"{API_ROOT}/search", params=params, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            it["id"]["videoId"]
            for it in items
            if it.get("id", {}).get("videoId")
        ]

    def _video_stats(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """videos.list -> snippet + statistics for each id (batched by 50)."""
        out: list[dict[str, Any]] = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            params = {
                "key": self.s.youtube_api_key,
                "part": "snippet,statistics",
                "id": ",".join(chunk),
                "maxResults": 50,
            }
            resp = self.session.get(f"{API_ROOT}/videos", params=params, timeout=30)
            resp.raise_for_status()
            out.extend(resp.json().get("items", []))
        return out

    def scrape_keywords(
        self, keywords: list[str], region: str | None = None
    ) -> list[dict[str, Any]]:
        """Search every keyword, enrich with stats, return raw video items."""
        if not keywords:
            return []
        ids: list[str] = []
        for kw in keywords:
            try:
                ids.extend(self._search_ids(kw, region))
            except Exception:  # one bad keyword must not kill the run
                log.exception("Search failed for keyword %r", kw)
        # de-dupe ids while preserving order
        seen: set[str] = set()
        unique_ids = [i for i in ids if not (i in seen or seen.add(i))]
        log.info(
            "YouTube search: %d keyword(s) -> %d unique video(s)",
            len(keywords),
            len(unique_ids),
        )
        if not unique_ids:
            return []
        return self._video_stats(unique_ids)


def summarize_inspiration(items: list[dict], top_n: int = 12) -> list[dict]:
    """Trim raw video items to the fields the LLM needs, ranked by engagement."""
    cleaned = []
    for it in items:
        snip = it.get("snippet", {})
        stats = it.get("statistics", {})
        title = (snip.get("title") or "").strip()
        if not title:
            continue
        views = int(stats.get("viewCount") or 0)
        likes = int(stats.get("likeCount") or 0)
        comments = int(stats.get("commentCount") or 0)
        cleaned.append(
            {
                "title": title[:200],
                "channel": (snip.get("channelTitle") or "").strip(),
                "views": views,
                "likes": likes,
                "comments": comments,
                # views dominate, but comments signal strong engagement
                "engagement": views + comments * 50,
                "published": (snip.get("publishedAt") or "")[:10],
                "url": f"https://youtu.be/{it.get('id', '')}",
                "description": (snip.get("description") or "").strip()[:300],
            }
        )
    cleaned.sort(key=lambda x: x["engagement"], reverse=True)
    return cleaned[:top_n]
