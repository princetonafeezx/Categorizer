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

def read_transaction_file(file_path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    transactions: list[dict[str, Any]] = []
    warnings: list[str] = []
    input_path = Path(file_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Could not find file: {input_path}")

    with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            return [], ["The file was empty."]

        column_map = detect_columns(headers)
        needed_indexes = {column_map["date"], column_map["merchant"], column_map["amount"]}
        if None in needed_indexes:
            warnings.append("I could not confidently find every column, so some rows may be skipped.")

        for line_number, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            try:
                cd = column_map["date"]
                cm = column_map["merchant"]
                ca = column_map["amount"]
                if cd is None or cm is None or ca is None:
                    raise ValueError("Row does not have enough columns")
                if max(cd, cm, ca) >= len(row):
                    raise ValueError("Row does not have enough columns")
                date_value = row[cd].strip()
                merchant_value = row[cm].strip()
                amount_value = parse_amount(row[ca])
                if not date_value or not merchant_value:
                    raise ValueError("Date or merchant was blank")
                transactions.append(
                    {
                        "date": date_value,
                        "merchant": merchant_value,
                        "amount": amount_value,
                    }
                )
            except (ValueError, TypeError) as error:
                warnings.append(f"Skipped line {line_number}: {error}")
    return transactions, warnings

def generate_mock_transactions() -> list[dict[str, Any]]:
    today = date.today()
    merchants = [
        ("Starbucks", 6.45),
        ("Starbuks", 5.95),
        ("Whole Foods", 84.20),
        ("Shell Oil", 47.83),
        ("Netflixx", 15.49),
        ("Spotify", 9.99),
        ("Amazon Marketplace", 42.18),
        ("Walgreens", 18.32),
        ("Comcast Cable", 79.99),
        ("Landlord Portal", 1450.00),
        ("Uber Trip", 23.50),
        ("Target", 61.70),
    ]

    transactions: list[dict[str, Any]] = []
    for index, (merchant, amount) in enumerate(merchants):
        transaction_date = today - timedelta(days=index * 2)
        transactions.append(
            {
                "date": transaction_date.isoformat(),
                "merchant": merchant,
                "amount": amount,
            }
        )
    return transactions

def find_best_rule_match(
    merchant: str, rules: dict[str, CategoryRule], threshold: float = 0.76
) -> RuleMatchResult:
    merchant_key = clean_text(merchant)
    best_key: str | None = None
    best_score = 0.0
    best_match_type = "unknown"

    for rule_key, payload in rules.items():
        normalized_rule = clean_text(rule_key)
        if not normalized_rule:
            continue
        if _exact_rule_matches(merchant_key, normalized_rule):
            return cast(
                RuleMatchResult,
                {
                    "category": payload["category"],
                    "subcategory": payload["subcategory"],
                    "confidence": 1.0,
                    "match_type": "exact",
                    "rule_key": rule_key,
                },
            )

        candidate_scores = [similarity_ratio(merchant_key, normalized_rule)]
        for word in merchant_key.split():
            candidate_scores.append(similarity_ratio(word, normalized_rule))
        score = max(candidate_scores)
        if score > best_score:
            best_score = score
            best_key = rule_key
            best_match_type = "fuzzy"

    if best_key is not None and best_score >= threshold:
        payload = rules[best_key]
        return cast(
            RuleMatchResult,
            {
                "category": payload["category"],
                "subcategory": payload["subcategory"],
                "confidence": round(best_score, 3),
                "match_type": best_match_type,
                "rule_key": best_key,
            },
        )

    return cast(
        RuleMatchResult,
        {
            "category": "Unknown",
            "subcategory": "Unknown",
            "confidence": round(best_score, 3),
            "match_type": "unknown",
            "rule_key": "",
        },
    )

def categorize_transactions(
    transactions: list[dict[str, Any]],
    rules: dict[str, CategoryRule] | None = None,
    threshold: float = 0.76,
) -> tuple[list[CategorizedRecord], list[CategorizedRecord]]:
    active_rules = rules or DEFAULT_RULES.copy()
    categorized: list[CategorizedRecord] = []
    flagged: list[CategorizedRecord] = []

    for transaction in transactions:
        match = find_best_rule_match(str(transaction.get("merchant", "")), active_rules, threshold)
        category = match["category"]
        if category not in VALID_CATEGORIES:
            category = "Unknown"
        sub_raw = str(match["subcategory"]).strip()
        subcategory = sub_raw if sub_raw else category
        try:
            amount = float(transaction["amount"])
        except (KeyError, TypeError, ValueError):
            amount = 0.0
        row = cast(
            CategorizedRecord,
            {
                "date": transaction.get("date", ""),
                "merchant": str(transaction.get("merchant", "")),
                "amount": amount,
                "category": category,
                "subcategory": subcategory,
                "confidence": float(match["confidence"]),
                "match_type": match["match_type"],
            },
        )
        categorized.append(row)

        if row["match_type"] == "fuzzy" and row["confidence"] < min(0.95, threshold + 0.10):
            flagged.append(row)
        elif row["match_type"] == "unknown":
            flagged.append(row)

    return categorized, flagged

def summarize_categories(
    records: list[dict[str, Any]] | Sequence[Mapping[str, Any]],
) -> list[CategorySummaryRow]:
    summary: dict[str, dict[str, Any]] = {}
    for record in records:
        category = str(record.get("category", "Unknown"))
        try:
            amount = float(record.get("amount", 0.0))
        except (TypeError, ValueError):
            amount = 0.0
        if category not in summary:
            summary[category] = {"category": category, "total": 0.0, "count": 0}
        summary[category]["total"] += amount
        summary[category]["count"] += 1

    rows = list(summary.values())
    rows.sort(key=lambda item: (-float(item["total"]), item["category"]))
    return cast(list[CategorySummaryRow], rows)



















def main() -> None:
    menu()


if __name__ == "__main__":
    main()
