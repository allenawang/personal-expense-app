"""Warnings and recommendations.

Each rule reads the month summary and, if it applies, returns one insight.
Insights are sorted by severity so the thing most likely to blow your budget
sits at the top of the dashboard.

Adding a new rule means writing one function and appending it to RULES.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.analytics import MonthSummary, money

SEVERITY_ORDER = {"alert": 0, "warning": 1, "tip": 2, "good": 3}


@dataclass(frozen=True)
class Insight:
    level: str  # alert | warning | tip | good
    title: str
    detail: str

    @property
    def rank(self) -> int:
        return SEVERITY_ORDER.get(self.level, 9)


def _fmt(amount: Decimal) -> str:
    return f"{money(amount):,.2f}"


# --- rules ------------------------------------------------------------------


def rule_overall_exceeded(summary: MonthSummary) -> list[Insight]:
    if summary.overall_limit is None or summary.total_spent <= summary.overall_limit:
        return []
    over = summary.total_spent - summary.overall_limit
    return [
        Insight(
            "alert",
            f"You're {_fmt(over)} past your monthly budget",
            f"Spent {_fmt(summary.total_spent)} against a {_fmt(summary.overall_limit)} limit "
            f"with {summary.window.days_remaining} days still to go.",
        )
    ]


def rule_overall_projection(summary: MonthSummary) -> list[Insight]:
    if summary.overall_limit is None or summary.overall_status != "at_risk":
        return []
    overshoot = summary.overall_projected - summary.overall_limit
    if overshoot <= 0:
        return []
    return [
        Insight(
            "warning",
            f"On pace to finish {_fmt(overshoot)} over budget",
            f"At the current rate the month lands near {_fmt(summary.overall_projected)}, "
            f"against a {_fmt(summary.overall_limit)} limit.",
        )
    ]


def rule_category_over(summary: MonthSummary) -> list[Insight]:
    insights = []
    for line in sorted(summary.tracked_lines, key=lambda l: l.spent - (l.limit or 0), reverse=True):
        if line.status != "over":
            continue
        over = line.spent - line.limit
        insights.append(
            Insight(
                "alert",
                f"{line.name} is {_fmt(over)} over its limit",
                f"{_fmt(line.spent)} spent against {_fmt(line.limit)}. "
                f"Pausing this category would free up {_fmt(over)} elsewhere.",
            )
        )
    return insights[:3]


def rule_category_at_risk(summary: MonthSummary) -> list[Insight]:
    insights = []
    for line in summary.tracked_lines:
        if line.status != "at_risk":
            continue
        pace_amount = line.pace_amount or Decimal("0")
        ahead = line.spent - pace_amount
        insights.append(
            Insight(
                "warning",
                f"{line.name} is running hot",
                f"{_fmt(line.spent)} spent where an even pace would be {_fmt(pace_amount)} "
                f"by now — {_fmt(ahead)} ahead. Projected month-end: {_fmt(line.projected)}.",
            )
        )
    insights.sort(key=lambda i: i.title)
    return insights[:3]


def rule_daily_allowance(summary: MonthSummary) -> list[Insight]:
    allowance = summary.daily_allowance
    if allowance is None or not summary.window.is_current:
        return []
    days = summary.window.days_remaining
    if allowance <= 0:
        return [
            Insight(
                "alert",
                "Nothing left in the budget this month",
                f"Every dollar spent over the next {days} days puts you further past the limit.",
            )
        ]
    return [
        Insight(
            "tip",
            f"{_fmt(allowance)} a day keeps you on budget",
            f"{_fmt(summary.overall_remaining)} left across {days} remaining days.",
        )
    ]


def rule_untracked_spending(summary: MonthSummary) -> list[Insight]:
    loose = summary.untracked_with_spend
    if not loose:
        return []
    total = sum((line.spent for line in loose), Decimal("0"))
    names = ", ".join(line.name for line in loose[:3])
    more = f" and {len(loose) - 3} more" if len(loose) > 3 else ""
    return [
        Insight(
            "tip",
            f"{_fmt(total)} is going to categories with no budget",
            f"{names}{more} have no monthly limit set, so they can't be tracked against a goal.",
        )
    ]


def rule_concentration(summary: MonthSummary) -> list[Insight]:
    if summary.total_spent <= 0 or not summary.lines:
        return []
    top = summary.lines[0]
    if top.share < 0.40:
        return []
    return [
        Insight(
            "tip",
            f"{top.name} is {top.share:.0%} of everything you spent",
            f"{_fmt(top.spent)} of {_fmt(summary.total_spent)}. "
            "The fastest way to change the total is to change this one number.",
        )
    ]


def rule_all_clear(summary: MonthSummary) -> list[Insight]:
    if summary.overall_limit is None or summary.total_spent <= 0:
        return []
    if summary.overall_status != "on_track":
        return []
    if any(line.status in {"over", "at_risk"} for line in summary.tracked_lines):
        return []
    return [
        Insight(
            "good",
            "Every category is on track",
            f"{_fmt(summary.total_spent)} spent, {_fmt(summary.overall_remaining)} still available.",
        )
    ]


def rule_no_budget_yet(summary: MonthSummary) -> list[Insight]:
    if summary.overall_limit is not None or summary.tracked_lines:
        return []
    return [
        Insight(
            "tip",
            "Set a budget to start tracking goals",
            "Once a monthly limit exists, this page shows pacing, projections, and warnings.",
        )
    ]


RULES = [
    rule_overall_exceeded,
    rule_overall_projection,
    rule_category_over,
    rule_category_at_risk,
    rule_daily_allowance,
    rule_untracked_spending,
    rule_concentration,
    rule_all_clear,
    rule_no_budget_yet,
]


def generate(summary: MonthSummary, limit: int = 6) -> list[Insight]:
    insights: list[Insight] = []
    for rule in RULES:
        insights.extend(rule(summary))
    insights.sort(key=lambda insight: insight.rank)
    return insights[:limit]
