"""Category management.

Categories are meant to be cheap to add and cheap to retire. A category with
no expenses can be deleted outright; one with history is archived instead, so
past months keep their labels and totals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Category, Expense

router = APIRouter(prefix="/categories", tags=["categories"])


def _expense_count(session: Session, category_id: int) -> int:
    return (
        session.execute(
            select(func.count(Expense.id)).where(Expense.category_id == category_id)
        ).scalar()
        or 0
    )


@router.post("")
def add_category(
    name: str = Form(...),
    color: str = Form(default="#4A6FA5"),
    icon: str = Form(default=""),
    redirect_to: str = Form(default="/categories"),
    session: Session = Depends(get_session),
):
    clean = name.strip()[:60]
    if not clean:
        raise HTTPException(status_code=400, detail="Give the category a name")

    existing = session.execute(
        select(Category).where(func.lower(Category.name) == clean.lower())
    ).scalar_one_or_none()
    if existing is not None:
        if existing.is_archived:
            existing.is_archived = False  # bringing a retired category back
            session.commit()
            return RedirectResponse(redirect_to, status_code=303)
        raise HTTPException(status_code=400, detail=f"{clean} already exists")

    highest = session.execute(select(func.max(Category.sort_order))).scalar() or 0
    session.add(
        Category(name=clean, color=color, icon=icon.strip()[:8], sort_order=highest + 1)
    )
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/{category_id}")
def update_category(
    category_id: int,
    name: str = Form(...),
    color: str = Form(...),
    icon: str = Form(default=""),
    redirect_to: str = Form(default="/categories"),
    session: Session = Depends(get_session),
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    category.name = name.strip()[:60] or category.name
    category.color = color
    category.icon = icon.strip()[:8]
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/{category_id}/archive")
def toggle_archive(
    category_id: int,
    redirect_to: str = Form(default="/categories"),
    session: Session = Depends(get_session),
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    category.is_archived = not category.is_archived
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/{category_id}/move")
def move_category(
    category_id: int,
    direction: str = Form(...),
    redirect_to: str = Form(default="/categories"),
    session: Session = Depends(get_session),
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    ordered = (
        session.execute(select(Category).order_by(Category.sort_order, Category.name))
        .scalars()
        .all()
    )
    index = next(i for i, item in enumerate(ordered) if item.id == category_id)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(ordered):
        ordered[index], ordered[target] = ordered[target], ordered[index]
        for position, item in enumerate(ordered):
            item.sort_order = position
        session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/{category_id}/delete")
def delete_category(
    category_id: int,
    redirect_to: str = Form(default="/categories"),
    session: Session = Depends(get_session),
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if _expense_count(session, category_id) > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{category.name} has expenses recorded against it. "
                "Archive it instead so past months keep their totals."
            ),
        )

    session.delete(category)
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)
