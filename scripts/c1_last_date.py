#!/usr/bin/env python3
"""Canonical C1 last-date metadata derived from actual daily series."""
from __future__ import annotations
import datetime as dt
import math
from typing import Any
ORIGIN = dt.date(2022, 1, 1)
def _last_valid_offset(rows: Any) -> int | None:
    if not isinstance(rows, list): return None
    for row in reversed(rows):
        if not isinstance(row, list) or len(row) < 2 or row[1] is None: continue
        try: off=int(row[0]); value=float(row[1])
        except (TypeError,ValueError): continue
        if math.isfinite(value): return off
    return None
def latest_daily_date(payload: dict[str,Any]) -> str:
    offsets=[]
    for short in ('G','S'):
        rows=((((payload.get(short) or {}).get('corse') or {}).get('d')) or [])
        off=_last_valid_offset(rows)
        if off is not None: offsets.append(off)
    if not offsets: raise ValueError('No valid C1 daily rows available for meta.last_date')
    return (ORIGIN+dt.timedelta(days=max(offsets))).isoformat()
def attach_last_date(meta: dict[str,Any] | None,payload: dict[str,Any]) -> dict[str,Any]:
    out=dict(meta or {}); out['last_date']=latest_daily_date(payload); return out
def validate_last_date(payload: dict[str,Any]) -> None:
    expected=latest_daily_date(payload); actual=((payload.get('meta') or {}).get('last_date'))
    if actual!=expected: raise ValueError(f'candidate meta.last_date mismatch: expected {expected}, got {actual!r}')
