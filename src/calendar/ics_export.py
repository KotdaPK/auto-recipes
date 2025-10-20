"""Build an ICS calendar for a week from a list of meal dicts."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from ics import Calendar, Event


def build_week_ics(meals: Iterable[dict], outfile: str) -> None:
    """meals: iterable of dicts with keys: title, start (datetime), duration_min, url(optional)"""
    cal = Calendar()
    for m in meals:
        ev = Event()
        ev.name = m.get("title")
        start = m.get("start")
        ev.begin = start
        ev.duration = timedelta(minutes=int(m.get("duration_min", 45)))
        if m.get("url"):
            ev.description = m.get("url")
        cal.events.add(ev)
    with open(outfile, "w", encoding="utf8") as fh:
        fh.writelines(cal)
