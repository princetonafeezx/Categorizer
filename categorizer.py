from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

from csv_columns import detect_columns
from parsing import parse_amount
from schemas import (
    CategorizedRecord,
    CategoryRule,
    CategorySummaryRow,
    ClassificationResult,
    RuleMatchResult,
)
from storage import format_money, load_merged_category_rules, save_rules_overrides
from textutil import clean_text, similarity_ratio

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"

VALID_CATEGORIES = {
    "Food & Drink",
    "Transportation",
    "Entertainment",
    "Shopping",
    "Utilities",
    "Health",
    "Housing",
    "Income",
    "Travel",
    "Other",
    "Unknown",
}

_MIN_EXACT_SUBSTRING_CHARS = 4

def _bounded_phrase_in_text(haystack: str, needle: str) -> bool:
    
    if not needle or needle not in haystack:
        return False
    start = 0
    needle_len = len(needle)
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return False
        before_ok = idx == 0 or haystack[idx - 1] == " "
        after_idx = idx + needle_len
        after_ok = after_idx == len(haystack) or haystack[after_idx] == " "
        if before_ok and after_ok:
            return True
        start = idx + 1

def _tokens_have_consecutive_phrase(merchant_tokens: list[str], rule: str) -> bool:
    rule_tokens = rule.split()
    if not rule_tokens:
        return False
    if len(rule_tokens) == 1:
        return rule_tokens[0] in merchant_tokens
    m, r = len(merchant_tokens), len(rule_tokens)
    if r > m:
        return False
    for i in range(m - r + 1):
        if merchant_tokens[i : i + r] == rule_tokens:
            return True
    return False

def _exact_rule_matches(merchant_key: str, normalized_rule: str) -> bool:
    if not normalized_rule:
        return False
    if merchant_key == normalized_rule:
        return True
    merchant_tokens = merchant_key.split()
    if _tokens_have_consecutive_phrase(merchant_tokens, normalized_rule):
        return True
    compact_rule_len = len(normalized_rule.replace(" ", ""))
    if compact_rule_len < _MIN_EXACT_SUBSTRING_CHARS:
        return False
    if _bounded_phrase_in_text(merchant_key, normalized_rule):
        return True
    if _bounded_phrase_in_text(normalized_rule, merchant_key):
        return True
    return False

DEFAULT_RULES: dict[str, CategoryRule] = {
    "starbucks": {"category": "Food & Drink", "subcategory": "Dining Out"},
    "whole foods": {"category": "Food & Drink", "subcategory": "Groceries"},
    "trader joe s": {"category": "Food & Drink", "subcategory": "Groceries"},
    "shell": {"category": "Transportation", "subcategory": "Transportation"},
    "chevron": {"category": "Transportation", "subcategory": "Transportation"},
    "uber": {"category": "Transportation", "subcategory": "Transportation"},
    "lyft": {"category": "Transportation", "subcategory": "Transportation"},
    "netflix": {"category": "Entertainment", "subcategory": "Entertainment"},
    "spotify": {"category": "Entertainment", "subcategory": "Entertainment"},
    "steam": {"category": "Entertainment", "subcategory": "Entertainment"},
    "amazon": {"category": "Shopping", "subcategory": "Shopping"},
    "target": {"category": "Shopping", "subcategory": "Shopping"},
    "walmart": {"category": "Shopping", "subcategory": "Shopping"},
    "cvs": {"category": "Health", "subcategory": "Health"},
    "walgreens": {"category": "Health", "subcategory": "Health"},
    "kaiser": {"category": "Health", "subcategory": "Insurance"},
    "comcast": {"category": "Utilities", "subcategory": "Utilities"},
    "pge": {"category": "Utilities", "subcategory": "Utilities"},
    "at&t": {"category": "Utilities", "subcategory": "Utilities"},
    "landlord": {"category": "Housing", "subcategory": "Rent"},
    "apartment": {"category": "Housing", "subcategory": "Rent"},
    "payroll": {"category": "Income", "subcategory": "Paycheck"},
}




















def main() -> None:
    menu()


if __name__ == "__main__":
    main()
