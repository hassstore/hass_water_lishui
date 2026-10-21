"""Shared fixtures and sample payloads for the Lishui water tests."""

from __future__ import annotations

from typing import Any

DOMAIN = "hass_water_lishui"

# Two billing periods, newest first, exactly like getFareList returns them.
FARES: list[dict[str, Any]] = [
    {
        "fareMonth": "2026-09",
        "fareValue": "42.50",
        "balance": "12.00",
        "currDegree": "1234.5",
        "lastDegree": "1200.0",
        "currCopyDate": "2026-09-05",
        "lastCopyDate": "2026-08-05",
        "billFlag": "0",
    },
    {
        "fareMonth": "2026-08",
        "fareValue": "38.00",
        "balance": "54.50",
        "currDegree": "1200.0",
        "lastDegree": "1170.0",
        "currCopyDate": "2026-08-05",
        "lastCopyDate": "2026-07-05",
        "billFlag": "1",
    },
]

ENTRY_DATA = {"card_no": "123456", "year": "2026", "token": "old-token"}
