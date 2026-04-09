"""Typed shapes for data flowing between ll_categorizer modules and the CLI.

These are documentation and static-check contracts; runtime still uses plain dicts.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from typing_extensions import NotRequired


class CategoryRule(TypedDict):
    """Merchant rule target for the categorizer."""

    category: str
    subcategory: str


class RuleMatchResult(TypedDict):
    """Output of :func:`categorizer.find_best_rule_match`."""

    category: str
    subcategory: str
    confidence: float
    match_type: str
    rule_key: str


class CategorizedRecord(TypedDict):
    """Single transaction row after classification or when loaded from CSV."""

    date: str | date
    merchant: str
    amount: float
    category: str
    subcategory: NotRequired[str]
    confidence: NotRequired[float]
    match_type: NotRequired[str]


class CategorySummaryRow(TypedDict):
    """One line from :func:`categorizer.summarize_categories`."""

    category: str
    total: float
    count: int


class ClassificationResult(TypedDict):
    """Return value of :func:`categorizer.run_classification`."""

    records: list[CategorizedRecord]
    flagged: list[CategorizedRecord]
    warnings: list[str]
    summary: list[CategorySummaryRow]
    rules: dict[str, CategoryRule]
