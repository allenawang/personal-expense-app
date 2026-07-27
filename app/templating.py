"""Shared Jinja2 environment.

Formatting filters live here so templates stay free of arithmetic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def money(value: Decimal | float | int | None) -> str:
    """1234.5 -> $1,234.50"""
    if value is None:
        return "—"
    return f"{settings.currency_symbol}{Decimal(str(value)):,.2f}"


def money_short(value: Decimal | float | int | None) -> str:
    """1234.5 -> $1,235 — for tight spaces where cents are noise."""
    if value is None:
        return "—"
    return f"{settings.currency_symbol}{Decimal(str(value)):,.0f}"


def day_label(value: date | None) -> str:
    """2026-06-05 -> 'Fri 5 Jun' (built by hand; %-d is not portable to Windows)."""
    if value is None:
        return ""
    if not hasattr(value, "strftime"):
        return str(value)
    return f"{value.strftime('%a')} {value.day} {value.strftime('%b')}"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


templates.env.filters["money"] = money
templates.env.filters["money_short"] = money_short
templates.env.filters["day"] = day_label
templates.env.filters["clamp"] = clamp
templates.env.globals["app_name"] = settings.app_name
templates.env.globals["currency"] = settings.currency_symbol
