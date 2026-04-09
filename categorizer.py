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
























def main() -> None:
    menu()


if __name__ == "__main__":
    main()
