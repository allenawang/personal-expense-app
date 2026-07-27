"""Setting and clearing monthly budget goals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Budget, Category

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _parse_limit(raw: str) -> Decimal | None:
    """Blank clears the limit; anything else must be a positive number."""
    text = (raw or "").replace(",", "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Enter the limit as a number, like 600")
    if value < 0:
        raise HTTPException(status_code=400, detail="A limit can't be negative")
    return value


def _set_limit(session: Session, category_id: int | None, limit: Decimal | None) -> None:
    existing = session.execute(
        select(Budget).where(
            Budget.category_id.is_(None)
            if category_id is None
            else Budget.category_id == category_id
        )
    ).scalar_one_or_none()

    if limit is None or limit == 0:
        if existing is not None:
            session.delete(existing)
        return

    if existing is None:
        session.add(Budget(category_id=category_id, monthly_limit=limit))
    else:
        existing.monthly_limit = limit


@router.post("/overall")
def set_overall_budget(
    monthly_limit: str = Form(default=""),
    redirect_to: str = Form(default="/budgets"),
    session: Session = Depends(get_session),
):
    _set_limit(session, None, _parse_limit(monthly_limit))
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/category/{category_id}")
def set_category_budget(
    category_id: int,
    monthly_limit: str = Form(default=""),
    redirect_to: str = Form(default="/budgets"),
    session: Session = Depends(get_session),
):
    if session.get(Category, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    _set_limit(session, category_id, _parse_limit(monthly_limit))
    session.commit()
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/bulk")
async def save_all_budgets(request: Request, session: Session = Depends(get_session)):
    """Save the whole budgets form in one pass.

    Fields arrive as `limit_overall` and `limit_<category_id>`. A blank field
    clears that limit, which is how you stop tracking a category.
    """
    form = await request.form()
    redirect_to = str(form.get("redirect_to") or "/budgets")

    _set_limit(session, None, _parse_limit(str(form.get("limit_overall", ""))))

    for category in session.execute(select(Category)).scalars():
        key = f"limit_{category.id}"
        if key in form:
            _set_limit(session, category.id, _parse_limit(str(form[key])))

    session.commit()
    return RedirectResponse(redirect_to, status_code=303)
