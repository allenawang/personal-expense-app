"""Month arithmetic.

Everything the app says about "on track" depends on how far through the month
you are, so that calculation lives in one place.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MonthWindow:
    year: int
    month: int
    start: date
    end: date  # inclusive
    days_in_month: int
    days_elapsed: int  # 1..days_in_month for the current month, else full month
    is_current: bool

    @property
    def days_remaining(self) -> int:
        return self.days_in_month - self.days_elapsed

    @property
    def pace(self) -> float:
        """Fraction of the month spent, 0.0-1.0. Used as the 'should have spent' line."""
        return self.days_elapsed / self.days_in_month

    @property
    def label(self) -> str:
        return self.start.strftime("%B %Y")

    @property
    def slug(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def month_window(year: int, month: int, today: date | None = None) -> MonthWindow:
    today = today or date.today()
    days_in_month = monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, days_in_month)
    is_current = (today.year, today.month) == (year, month)

    if is_current:
        days_elapsed = today.day
    elif today > end:
        days_elapsed = days_in_month  # a finished month
    else:
        days_elapsed = 0  # a future month

    return MonthWindow(
        year=year,
        month=month,
        start=start,
        end=end,
        days_in_month=days_in_month,
        days_elapsed=days_elapsed,
        is_current=is_current,
    )


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def recent_months(count: int, today: date | None = None) -> list[tuple[int, int]]:
    """The last `count` months ending with the current one, oldest first."""
    today = today or date.today()
    return [shift_month(today.year, today.month, -offset) for offset in range(count - 1, -1, -1)]
