"""Starter categories, created only when the database has none.

These are a starting point, not a fixed list — rename, recolor, reorder,
archive, or delete any of them from the Categories page.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category

STARTERS = [
    ("Groceries", "#3F7D58", "🛒"),
    ("Eating out", "#C4643A", "🍜"),
    ("Transit", "#3E6EA8", "🚇"),
    ("Rent & bills", "#5B5F73", "🏠"),
    ("Health", "#8C4A6B", "💊"),
    ("Fun", "#B08528", "🎟️"),
]


def seed_starter_categories(session: Session) -> None:
    existing = session.execute(select(func.count(Category.id))).scalar() or 0
    if existing:
        return

    for order, (name, color, icon) in enumerate(STARTERS):
        session.add(Category(name=name, color=color, icon=icon, sort_order=order))
    session.commit()
