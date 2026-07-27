"""Adding and removing expenses."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Category, Expense

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _parse_amount(raw: str) -> Decimal:
    try:
        amount = Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise HTTPException(status_code=400, detail="Enter the amount as a number, like 24.50")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    return amount


@router.post("")
def add_expense(
    amount: str = Form(...),
    category_id: int = Form(...),
    spent_on: date = Form(...),
    note: str = Form(default=""),
    redirect_to: str = Form(default="/"),
    session: Session = Depends(get_session),
):
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="That category no longer exists")

    session.add(
        Expense(
            amount=_parse_amount(amount),
            category_id=category_id,
            spent_on=spent_on,
            note=note.strip()[:200],
        )
    )
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/{expense_id}/delete")
def delete_expense(
    expense_id: int,
    redirect_to: str = Form(default="/"),
    session: Session = Depends(get_session),
):
    expense = session.get(Expense, expense_id)
    if expense is not None:
        session.delete(expense)
        session.commit()
    return RedirectResponse(redirect_to, status_code=303)
