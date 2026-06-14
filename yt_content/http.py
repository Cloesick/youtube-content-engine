"""Shared HTTP helper: a requests session with retry + backoff.

Handles rate-limit (429) and transient 5xx errors you hit when running across
many channels / many API calls in one job.
"""
from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter, Retry

log = logging.getLogger("yt_content.http")


def make_session(total_retries: int = 5) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=1.5,  # 0s, 1.5s, 3s, 6s, 12s ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "PATCH"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
