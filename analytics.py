"""Spend rollups, pacing, and projections.

The vocabulary used throughout:

  spent      what has actually left your account this month, per category
  limit      the monthly budget you set for that category
  pace       where spending *should* be today if the limit were spread evenly
  projected  where the month ends if you keep spending at the current rate
  status     on_track | at_risk | over | untracked

Nothing here touches HTTP or templates, which makes it directly testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Expense
from app.services.periods import MonthWindow, month_window, recent_months

ZERO = Decimal("0.00")

# How far ahead of pace you can drift before the app flags it.
AT_RISK_MARGIN = 1.10  # 10% ahead of an even burn rate


def money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CategoryLine:
    """One row of the dashboard: a category measured against its budget."""

    category_id: int
    name: str
    color: str
    icon: str
    spent: Decimal
    limit: Decimal | None
    projected: Decimal
    status: str
    share: float  # portion of this month's total spend, 0.0-1.0
    transaction_count: int

    @property
    def is_tracked(self) -> bool:
        return self.limit is not None and self.limit > 0

    @property
    def remaining(self) -> Decimal | None:
        if not self.is_tracked:
            return None
        return money(self.limit - self.spent)

    @property
    def pace_amount(self) -> Decimal | None:
        """What you'd have spent by today at an even burn rate."""
        if not self.is_tracked:
            return None
        return money(self.limit * Decimal(str(self._pace)))

    @property
    def fill_pct(self) -> float:
        """Spent as a percentage of the limit, uncapped so overruns are visible."""
        if not self.is_tracked:
            return 0.0
        return float(self.spent / self.limit) * 100

    @property
    def projected_pct(self) -> float:
        if not self.is_tracked:
            return 0.0
        return float(self.projected / self.limit) * 100

    @property
    def pace_pct(self) -> float:
        return self._pace * 100

    # Set by MonthSummary after construction so the row knows the month context.
    _pace: float = field(default=0.0, repr=False)


@dataclass
class MonthSummary:
    window: MonthWindow
    lines: list[CategoryLine]
    total_spent: Decimal
    overall_limit: Decimal | None
    overall_projected: Decimal
    overall_status: str
    transaction_count: int

    @property
    def overall_remaining(self) -> Decimal | None:
        if self.overall_limit is None:
            return None
        return money(self.overall_limit - self.total_spent)

    @property
    def daily_allowance(self) -> Decimal | None:
        """What you can spend per day for the rest of the month and still land on budget."""
        remaining = self.overall_remaining
        if remaining is None or self.window.days_remaining <= 0:
            return None
        if remaining <= 0:
            return ZERO
        return money(remaining / self.window.days_remaining)

    @property
    def tracked_lines(self) -> list[CategoryLine]:
        return [line for line in self.lines if line.is_tracked]

    @property
    def untracked_with_spend(self) -> list[CategoryLine]:
        return [line for line in self.lines if not line.is_tracked and line.spent > 0]


def classify(spent: Decimal, limit: Decimal | None, pace: float) -> str:
    """Turn raw numbers into one of four states."""
    if limit is None or limit <= 0:
        return "untracked"
    if spent > limit:
        return "over"
    if pace <= 0:
        return "on_track"
    expected = limit * Decimal(str(pace))
    if expected > 0 and spent > expected * Decimal(str(AT_RISK_MARGIN)):
        return "at_risk"
    return "on_track"


def project(spent: Decimal, pace: float) -> Decimal:
    """Extrapolate month-end spend from the burn rate so far."""
    if pace <= 0:
        return money(spent)
    return money(spent / Decimal(str(pace)))


def build_summary(session: Session, year: int, month: int, today: date | None = None) -> MonthSummary:
    window = month_window(year, month, today=today)
    pace = window.pace

    totals = dict(
        session.execute(
            select(Expense.category_id, func.sum(Expense.amount))
            .where(Expense.spent_on.between(window.start, window.end))
            .group_by(Expense.category_id)
        ).all()
    )
    counts = dict(
        session.execute(
            select(Expense.category_id, func.count(Expense.id))
            .where(Expense.spent_on.between(window.start, window.end))
            .group_by(Expense.category_id)
        ).all()
    )

    budgets = {
        budget.category_id: money(budget.monthly_limit)
        for budget in session.execute(select(Budget)).scalars()
    }
    overall_limit = budgets.get(None)

    categories = (
        session.execute(
            select(Category).order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )

    total_spent = money(sum(totals.values(), Decimal("0")))

    lines: list[CategoryLine] = []
    for category in categories:
        spent = money(totals.get(category.id, ZERO))
        if category.is_archived and spent == 0:
            continue  # retired bucket with nothing in it this month
        limit = budgets.get(category.id)
        lines.append(
            CategoryLine(
                category_id=category.id,
                name=category.name,
                color=category.color,
                icon=category.icon,
                spent=spent,
                limit=limit,
                projected=project(spent, pace),
                status=classify(spent, limit, pace),
                share=float(spent / total_spent) if total_spent > 0 else 0.0,
                transaction_count=counts.get(category.id, 0),
                _pace=pace,
            )
        )

    # Biggest spend first, but keep zero-spend budgeted buckets visible below.
    lines.sort(key=lambda line: (line.spent == 0, -float(line.spent), line.name))

    return MonthSummary(
        window=window,
        lines=lines,
        total_spent=total_spent,
        overall_limit=overall_limit,
        overall_projected=project(total_spent, pace),
        overall_status=classify(total_spent, overall_limit, pace),
        transaction_count=sum(counts.values()),
    )


def daily_cumulative(session: Session, window: MonthWindow) -> list[dict]:
    """Running total for each day of the month, for the burn-down chart."""
    rows = session.execute(
        select(Expense.spent_on, func.sum(Expense.amount))
        .where(Expense.spent_on.between(window.start, window.end))
        .group_by(Expense.spent_on)
        .order_by(Expense.spent_on)
    ).all()
    per_day = {row[0]: money(row[1]) for row in rows}

    series: list[dict] = []
    running = ZERO
    for day in range(1, window.days_in_month + 1):
        current = date(window.year, window.month, day)
        running += per_day.get(current, ZERO)
        # Don't draw a flat line into the future.
        known = (not window.is_current) or day <= window.days_elapsed
        series.append({"day": day, "total": float(running) if known else None})
    return series


def monthly_history(session: Session, months: int = 6, today: date | None = None) -> list[dict]:
    """Totals for the last N months, for the trend chart."""
    history: list[dict] = []
    for year, month in recent_months(months, today=today):
        window = month_window(year, month, today=today)
        total = session.execute(
            select(func.sum(Expense.amount)).where(
                Expense.spent_on.between(window.start, window.end)
            )
        ).scalar()
        history.append(
            {
                "label": window.start.strftime("%b"),
                "slug": window.slug,
                "total": float(money(total)),
            }
        )
    return history
