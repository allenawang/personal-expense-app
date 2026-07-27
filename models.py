"""Domain models.

Three tables carry the whole app:

  Category  a spending bucket you define ("Groceries", "Transit")
  Expense   one thing you spent money on, on one day, in one category
  Budget    a monthly limit, either for one category or for everything

Categories are archived rather than deleted once they have history, so old
months keep their labels. A category with no expenses can be deleted outright.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#4A6FA5", nullable=False)
    icon: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="category")
    budget: Mapped["Budget | None"] = relationship(
        back_populates="category", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Category {self.name!r}>"


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_spent_on", "spent_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    spent_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    category: Mapped[Category] = relationship(back_populates="expenses")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Expense {self.amount} on {self.spent_on}>"


class Budget(Base):
    """A monthly ceiling.

    category_id NULL means the overall budget for the whole month.
    """

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", name="uq_budget_per_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    category: Mapped[Category | None] = relationship(back_populates="budget")

    @property
    def is_overall(self) -> bool:
        return self.category_id is None
