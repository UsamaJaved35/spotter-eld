"""Turn a continuous duty log into one FMCSA record-of-duty-status sheet per day.

A record of duty status covers "one calendar day - 24 hours", so any segment
that straddles midnight is split, and every sheet is padded with off-duty time
until its four totals add up to exactly 24 hours, as 395.8 requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .types import DutySegment, DutyStatus, StopKind

#: The printed grid is marked in 15-minute increments.
GRID_RESOLUTION_HOURS = 0.25


@dataclass
class LogEntry:
    """One horizontal run on the grid, in hours from midnight."""

    status: DutyStatus
    start_hour: float
    end_hour: float
    kind: StopKind = StopKind.OFF_DUTY
    note: str = ""
    location: str = ""
    miles: float = 0.0

    @property
    def hours(self) -> float:
        return self.end_hour - self.start_hour


@dataclass
class LogRemark:
    """A city/state annotation dropped under the grid at a duty change."""

    hour: float
    location: str
    note: str = ""
    status: DutyStatus = DutyStatus.OFF


@dataclass
class DailyLog:
    date: date
    entries: list[LogEntry] = field(default_factory=list)
    remarks: list[LogRemark] = field(default_factory=list)
    totals: dict[DutyStatus, float] = field(default_factory=dict)
    total_miles: float = 0.0

    @property
    def total_hours(self) -> float:
        return sum(self.totals.values())


def _split_at_midnight(segments: list[DutySegment]) -> dict[date, list[LogEntry]]:
    """Bucket segments by calendar day, cutting any that cross midnight.

    Miles are apportioned across the cut in proportion to time.
    """
    by_day: dict[date, list[LogEntry]] = {}

    for seg in segments:
        cursor = seg.start
        total_seconds = (seg.end - seg.start).total_seconds()

        while cursor < seg.end:
            day = cursor.date()
            next_midnight = datetime.combine(day + timedelta(days=1), time.min)
            chunk_end = min(seg.end, next_midnight)

            chunk_seconds = (chunk_end - cursor).total_seconds()
            share = (chunk_seconds / total_seconds) if total_seconds else 0.0
            day_start = datetime.combine(day, time.min)

            by_day.setdefault(day, []).append(
                LogEntry(
                    status=seg.status,
                    start_hour=(cursor - day_start).total_seconds() / 3600.0,
                    end_hour=(chunk_end - day_start).total_seconds() / 3600.0,
                    kind=seg.kind,
                    note=seg.note,
                    location=seg.location,
                    miles=seg.miles * share,
                )
            )
            cursor = chunk_end

    return by_day


def _pad_to_full_day(entries: list[LogEntry]) -> list[LogEntry]:
    """Fill any uncovered part of the grid with off-duty time."""
    padded: list[LogEntry] = []
    cursor = 0.0

    for entry in entries:
        if entry.start_hour - cursor > 1e-9:
            padded.append(LogEntry(DutyStatus.OFF, cursor, entry.start_hour, StopKind.OFF_DUTY))
        padded.append(entry)
        cursor = entry.end_hour

    if 24.0 - cursor > 1e-9:
        padded.append(LogEntry(DutyStatus.OFF, cursor, 24.0, StopKind.OFF_DUTY))

    return padded


def _totals(entries: list[LogEntry]) -> dict[DutyStatus, float]:
    """Per-status hour totals, nudged so the column adds to exactly 24.

    395.8 requires the four totals to equal 24; float drift from route durations
    must not show up as 23.99 on a printed sheet.
    """
    totals = {status: 0.0 for status in DutyStatus}
    for entry in entries:
        totals[entry.status] += entry.hours

    rounded = {status: round(hours, 2) for status, hours in totals.items()}
    drift = round(24.0 - sum(rounded.values()), 2)
    if drift:
        largest = max(rounded, key=lambda s: rounded[s])
        rounded[largest] = round(rounded[largest] + drift, 2)
    return rounded


def _remarks(entries: list[LogEntry]) -> list[LogRemark]:
    """One remark per change of duty status, per 395.8's Remarks requirement."""
    remarks: list[LogRemark] = []
    previous: DutyStatus | None = None

    for entry in entries:
        if entry.status is not previous and entry.location:
            remarks.append(
                LogRemark(
                    hour=entry.start_hour,
                    location=entry.location,
                    note=entry.note,
                    status=entry.status,
                )
            )
        previous = entry.status

    return remarks


def build_daily_logs(segments: list[DutySegment]) -> list[DailyLog]:
    """Build one :class:`DailyLog` per calendar day the trip touches."""
    if not segments:
        return []

    logs: list[DailyLog] = []
    for day, entries in sorted(_split_at_midnight(segments).items()):
        entries.sort(key=lambda e: e.start_hour)
        padded = _pad_to_full_day(entries)
        logs.append(
            DailyLog(
                date=day,
                entries=padded,
                remarks=_remarks(padded),
                totals=_totals(padded),
                total_miles=round(sum(e.miles for e in padded), 1),
            )
        )

    return logs
