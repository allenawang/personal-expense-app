"""HTML page routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Budget, Category, Expense
from app.services import analytics, insights
from app.services.periods import month_window, shift_month
from app.templating import templates

router = APIRouter()


def _requested_month(month: str | None) -> tuple[int, int]:
    """Parse ?month=YYYY-MM, falling back to today."""
    today = date.today()
    if not month:
        return today.year, today.month
    try:
        year_part, month_part = month.split("-")
        year, month_number = int(year_part), int(month_part)
        if 1 <= month_number <= 12 and 2000 <= year <= 2100:
            return year, month_number
    except (ValueError, AttributeError):
        pass
    return today.year, today.month


def _month_context(session: Session, month: str | None) -> dict:
    year, month_number = _requested_month(month)
    summary = analytics.build_summary(session, year, month_number)
    previous = shift_month(year, month_number, -1)
    following = shift_month(year, month_number, 1)
    return {
        "summary": summary,
        "window": summary.window,
        "prev_slug": f"{previous[0]:04d}-{previous[1]:02d}",
        "next_slug": f"{following[0]:04d}-{following[1]:02d}",
    }


@router.get("/")
def dashboard(
    request: Request,
    month: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    context = _month_context(session, month)
    window = context["window"]

    recent = (
        session.execute(
            select(Expense)
            .options(joinedload(Expense.category))
            .order_by(desc(Expense.spent_on), desc(Expense.id))
            .limit(8)
        )
        .scalars()
        .all()
    )
    active_categories = (
        session.execute(
            select(Category)
            .where(Category.is_archived.is_(False))
            .order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            **context,
            "page": "dashboard",
            "insights": insights.generate(context["summary"]),
            "recent": recent,
            "categories": active_categories,
            "today": min(date.today(), window.end).isoformat(),
        },
    )


@router.get("/expenses")
def expenses_page(
    request: Request,
    month: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
):
    context = _month_context(session, month)
    window = context["window"]

    query = (
        select(Expense)
        .options(joinedload(Expense.category))
        .where(Expense.spent_on.between(window.start, window.end))
        .order_by(desc(Expense.spent_on), desc(Expense.id))
    )
    if category_id:
        query = query.where(Expense.category_id == category_id)

    rows = session.execute(query).scalars().all()
    active_categories = (
        session.execute(
            select(Category)
            .where(Category.is_archived.is_(False))
            .order_by(Category.sort_order, Category.name)
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "expenses.html",
        {
            **context,
            "page": "expenses",
            "expenses": rows,
            "categories": active_categories,
            "active_filter": category_id,
            "today": min(date.today(), window.end).isoformat(),
        },
    )


@router.get("/budgets")
def budgets_page(
    request: Request,
    month: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    context = _month_context(session, month)
    overall = session.execute(
        select(Budget).where(Budget.category_id.is_(None))
    ).scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "budgets.html",
        {
            **context,
            "page": "budgets",
            "overall_budget": overall,
        },
    )


@router.get("/categories")
def categories_page(
    request: Request,
    month: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    context = _month_context(session, month)
    window = context["window"]

    categories = (
        session.execute(select(Category).order_by(Category.sort_order, Category.name))
        .scalars()
        .all()
    )
    usage = dict(
        session.execute(
            select(Expense.category_id, func.count(Expense.id)).group_by(Expense.category_id)
        ).all()
    )

    return templates.TemplateResponse(
        request,
        "categories.html",
        {
            **context,
            "page": "categories",
            "categories": categories,
            "usage": usage,
            "window": window,
        },
    )
