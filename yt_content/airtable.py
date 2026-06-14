"""Airtable client — the control plane.

Two tables:
  * YT Channels: one row per channel/niche (config). See README for schema.
  * YT Content Queue: generated video ideas with a Status lifecycle
    (Idea -> Scripted -> Filmed -> Published / Archived).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .config import Settings
from .http import make_session

log = logging.getLogger("yt_content.airtable")

API_ROOT = "https://api.airtable.com/v0"


@dataclass
class Channel:
    record_id: str
    name: str
    niche: str
    keywords: list[str]
    competitor_channels: list[str]
    tone: str
    active: bool
    ideas_per_run: int | None
    cta: str | None
    lead_magnet: str | None
    region: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    # comma- or newline-separated string
    parts = str(value).replace("\n", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


class AirtableClient:
    def __init__(self, settings: Settings):
        if not settings.airtable_token:
            raise RuntimeError("AIRTABLE_TOKEN is not set.")
        if not settings.airtable_base_id:
            raise RuntimeError("YT_AIRTABLE_BASE_ID is not set.")
        self.s = settings
        self.session = make_session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.airtable_token}",
                "Content-Type": "application/json",
            }
        )

    def _url(self, table: str) -> str:
        return f"{API_ROOT}/{self.s.airtable_base_id}/{quote(table)}"

    # ---- reads ----
    def _list(self, table: str, params: dict | None = None) -> list[dict]:
        url = self._url(table)
        records: list[dict] = []
        offset = None
        while True:
            q = dict(params or {})
            if offset:
                q["offset"] = offset
            resp = self.session.get(url, params=q, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
        return records

    def get_active_channels(self) -> list[Channel]:
        rows = self._list(self.s.channels_table)
        channels: list[Channel] = []
        for r in rows:
            f = r.get("fields", {})
            active = bool(f.get("Active", False))
            if not active:
                continue
            channels.append(
                Channel(
                    record_id=r["id"],
                    name=str(f.get("Name", "")).strip(),
                    niche=str(f.get("Niche", "")).strip(),
                    keywords=_split_list(f.get("Keywords")),
                    competitor_channels=_split_list(f.get("Competitor Channels")),
                    tone=str(f.get("Tone", "friendly, expert")).strip(),
                    active=active,
                    ideas_per_run=(
                        int(f["Ideas Per Run"])
                        if f.get("Ideas Per Run") not in (None, "")
                        else None
                    ),
                    cta=(f.get("CTA") or None),
                    lead_magnet=(f.get("Lead Magnet") or None),
                    region=(f.get("Region") or None),
                    raw=f,
                )
            )
        return channels

    def existing_dedupe_keys(self, channel_name: str) -> set[str]:
        """Dedupe keys already in the queue for this channel, so reruns don't
        create duplicate ideas."""
        formula = f"{{Channel}} = '{channel_name.replace(chr(39), '')}'"
        rows = self._list(
            self.s.queue_table,
            params={"filterByFormula": formula, "fields[]": "Dedupe Key"},
        )
        return {
            str(r.get("fields", {}).get("Dedupe Key", "")).strip()
            for r in rows
            if r.get("fields", {}).get("Dedupe Key")
        }

    # ---- writes ----
    def create_ideas(self, records: list[dict]) -> int:
        """Batch-create queue rows (Airtable caps at 10 per request)."""
        url = self._url(self.s.queue_table)
        created = 0
        batch: list[dict] = [{"fields": rec} for rec in records]
        for i in range(0, len(batch), 10):
            chunk = batch[i : i + 10]
            resp = self.session.post(
                url, json={"records": chunk, "typecast": True}, timeout=30
            )
            resp.raise_for_status()
            created += len(resp.json().get("records", []))
        return created

    def update_record(self, table: str, record_id: str, fields: dict) -> None:
        url = f"{self._url(table)}/{record_id}"
        resp = self.session.patch(
            url, json={"fields": fields, "typecast": True}, timeout=30
        )
        resp.raise_for_status()
