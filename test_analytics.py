"""Tests for the budget maths — the part that must not be quietly wrong."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Budget, Category, Expense
from app.services import analytics, insights
from app.services.periods import month_window, recent_months, shift_month


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        yield db


@pytest.fixture
def groceries(session):
    category = Category(name="Groceries", color="#3F7D58", sort_order=0)
    session.add(category)
    session.commit()
    return category


def add_expense(session, category, amount, day, month=6, year=2026):
    session.add(
        Expense(
            amount=Decimal(str(amount)),
            category_id=category.id,
            spent_on=date(year, month, day),
        )
    )
    session.commit()


# --- periods ----------------------------------------------------------------


def test_pace_is_fraction_of_month_elapsed():
    window = month_window(2026, 6, today=date(2026, 6, 15))
    assert window.days_in_month == 30
    assert window.days_elapsed == 15
    assert window.pace == pytest.approx(0.5)
    assert window.days_remaining == 15


def test_finished_month_is_fully_elapsed():
    window = month_window(2026, 5, today=date(2026, 6, 15))
    assert window.pace == 1.0
    assert not window.is_current


def test_future_month_has_not_started():
    window = month_window(2026, 12, today=date(2026, 6, 15))
    assert window.days_elapsed == 0
    assert window.pace == 0.0


def test_shift_month_crosses_year_boundaries():
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)


def test_recent_months_ends_with_current():
    months = recent_months(3, today=date(2026, 2, 10))
    assert months == [(2025, 12), (2026, 1), (2026, 2)]


# --- classification ---------------------------------------------------------


def test_spending_at_an_even_pace_is_on_track():
    assert analytics.classify(Decimal("50"), Decimal("100"), 0.5) == "on_track"


def test_spending_well_ahead_of_pace_is_at_risk():
    assert analytics.classify(Decimal("80"), Decimal("100"), 0.5) == "at_risk"


def test_spending_past_the_limit_is_over():
    assert analytics.classify(Decimal("120"), Decimal("100"), 0.5) == "over"


def test_category_without_a_limit_is_untracked():
    assert analytics.classify(Decimal("80"), None, 0.5) == "untracked"


def test_slight_overshoot_stays_on_track():
    """A few percent ahead shouldn't trigger a warning every single day."""
    assert analytics.classify(Decimal("53"), Decimal("100"), 0.5) == "on_track"


# --- projection -------------------------------------------------------------


def test_projection_extrapolates_the_burn_rate():
    # $150 spent halfway through the month projects to $300.
    assert analytics.project(Decimal("150"), 0.5) == Decimal("300.00")


def test_projection_of_a_finished_month_is_the_actual_total():
    assert analytics.project(Decimal("150"), 1.0) == Decimal("150.00")


# --- summary ----------------------------------------------------------------


def test_summary_rolls_up_spend_and_flags_the_category(session, groceries):
    session.add(Budget(category_id=groceries.id, monthly_limit=Decimal("300")))
    session.commit()
    add_expense(session, groceries, "200.00", day=5)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    line = summary.lines[0]

    assert summary.total_spent == Decimal("200.00")
    assert line.limit == Decimal("300.00")
    assert line.remaining == Decimal("100.00")
    assert line.pace_amount == Decimal("150.00")  # half of $300 at day 15
    assert line.status == "at_risk"
    assert line.projected == Decimal("400.00")


def test_expenses_outside_the_month_are_excluded(session, groceries):
    add_expense(session, groceries, "50.00", day=28, month=5)
    add_expense(session, groceries, "10.00", day=2, month=6)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    assert summary.total_spent == Decimal("10.00")


def test_daily_allowance_spreads_what_is_left(session, groceries):
    session.add(Budget(category_id=None, monthly_limit=Decimal("600")))
    session.commit()
    add_expense(session, groceries, "300.00", day=5)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    # $300 left over 15 remaining days.
    assert summary.daily_allowance == Decimal("20.00")


def test_archived_category_with_no_spend_is_hidden(session, groceries):
    groceries.is_archived = True
    session.commit()

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    assert summary.lines == []


def test_archived_category_still_shows_its_history(session, groceries):
    add_expense(session, groceries, "40.00", day=3)
    groceries.is_archived = True
    session.commit()

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    assert len(summary.lines) == 1
    assert summary.lines[0].spent == Decimal("40.00")


def test_burn_down_series_stops_at_today(session, groceries):
    add_expense(session, groceries, "25.00", day=2)
    window = month_window(2026, 6, today=date(2026, 6, 15))

    series = analytics.daily_cumulative(session, window)
    assert len(series) == 30
    assert series[1]["total"] == 25.0
    assert series[14]["total"] == 25.0  # day 15, still known
    assert series[15]["total"] is None  # day 16 hasn't happened


# --- insights ---------------------------------------------------------------


def test_going_over_budget_produces_an_alert(session, groceries):
    session.add(Budget(category_id=None, monthly_limit=Decimal("100")))
    session.commit()
    add_expense(session, groceries, "150.00", day=5)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    found = insights.generate(summary)

    assert found[0].level == "alert"
    assert "past your monthly budget" in found[0].title


def test_staying_on_track_produces_a_positive_note(session, groceries):
    session.add(Budget(category_id=None, monthly_limit=Decimal("600")))
    session.add(Budget(category_id=groceries.id, monthly_limit=Decimal("400")))
    session.commit()
    add_expense(session, groceries, "180.00", day=5)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    levels = {insight.level for insight in insights.generate(summary)}

    assert "alert" not in levels
    assert "good" in levels


def test_unbudgeted_spending_is_surfaced(session, groceries):
    add_expense(session, groceries, "75.00", day=4)

    summary = analytics.build_summary(session, 2026, 6, today=date(2026, 6, 15))
    titles = " ".join(insight.title for insight in insights.generate(summary))

    assert "no budget" in titles
