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






















def main() -> None:
    menu()


if __name__ == "__main__":
    main()
