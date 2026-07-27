"""JSON used by the charts on the dashboard.

Kept separate from the page routes so the browser can refresh chart data
without re-rendering HTML, and so the numbers are easy to inspect by hand.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import analytics

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/charts")
def chart_data(
    month: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    today = date.today()
    year, month_number = today.year, today.month
    if month:
        try:
            year, month_number = (int(part) for part in month.split("-"))
        except ValueError:
            pass

    summary = analytics.build_summary(session, year, month_number)
    window = summary.window

    return {
        "month": window.slug,
        "label": window.label,
        "currency": "$",
        "byCategory": [
            {
                "name": line.name,
                "color": line.color,
                "spent": float(line.spent),
                "limit": float(line.limit) if line.limit is not None else None,
            }
            for line in summary.lines
            if line.spent > 0 or line.limit
        ],
        "burnDown": {
            "series": analytics.daily_cumulative(session, window),
            "limit": float(summary.overall_limit) if summary.overall_limit else None,
            "daysInMonth": window.days_in_month,
            "daysElapsed": window.days_elapsed,
        },
        "history": analytics.monthly_history(session, months=6),
    }
