"""Tests for transaction categorization and CSV import."""

from __future__ import annotations

from pathlib import Path

import pytest
import categorizer
from schemas import CategoryRule


def test_run_classification_mock_has_records_and_summary() -> None:
    result = categorizer.run_classification(use_mock=True)
    assert len(result["records"]) >= 1
    assert result["warnings"] == []
    assert any(row["category"] != "Unknown" for row in result["records"])


def test_find_best_rule_match_starbucks_exact() -> None:
    rules: dict[str, CategoryRule] = {"starbucks": {"category": "Food & Drink", "subcategory": "Dining Out"}}
    match = categorizer.find_best_rule_match("Starbucks Downtown", rules, threshold=0.5)
    assert match["match_type"] == "exact"
    assert match["category"] == "Food & Drink"


def test_find_best_rule_match_fuzzy_typos() -> None:
    match = categorizer.find_best_rule_match("Starbuks", categorizer.DEFAULT_RULES, threshold=0.7)
    assert match["category"] == "Food & Drink"


def test_read_transaction_file_parses_minimal_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "stmt.csv"
    csv_path.write_text("Date,Description,Amount\n2024-06-01,Coffee Shop,5.25\n", encoding="utf-8")
    rows, warnings = categorizer.read_transaction_file(csv_path)
    assert len(rows) == 1
    assert rows[0]["merchant"] == "Coffee Shop"
    assert rows[0]["amount"] == pytest.approx(5.25)
    assert not warnings


def test_categorize_transactions_applies_rules() -> None:
    tx = [{"date": "2024-01-01", "merchant": "Whole Foods Market", "amount": 40.0}]
    rules: dict[str, CategoryRule] = {"whole foods": {"category": "Food & Drink", "subcategory": "Groceries"}}
    categorized, flagged = categorizer.categorize_transactions(tx, rules=rules, threshold=0.76)
    assert categorized[0]["category"] == "Food & Drink"


def test_summarize_categories_tolerates_sparse_rows() -> None:
    rows = categorizer.summarize_categories([{"category": "A", "amount": 10.0}, {"amount": "not-num"}, {}])
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["A"]["total"] == pytest.approx(10.0)
    assert by_cat["Unknown"]["count"] == 2


def test_detect_columns_matches_analysis_scoring() -> None:
    mapping = categorizer.detect_columns(["Date", "Description", "Amount"])
    assert mapping["date"] == 0
    assert mapping["merchant"] == 1
    assert mapping["amount"] == 2


def test_detect_columns_drops_unrecognized_date_header() -> None:
    mapping = categorizer.detect_columns(["Runtime", "Description", "Amount"])
    assert mapping["date"] is None
    assert mapping["merchant"] == 1
    assert mapping["amount"] == 2


def test_short_rule_key_no_substring_false_positive() -> None:
    rules: dict[str, CategoryRule] = {"at": {"category": "Utilities", "subcategory": "Phone"}}
    match = categorizer.find_best_rule_match("Patagonia Outfitters", rules, threshold=0.99)
    assert match["match_type"] == "unknown"
    assert match["category"] == "Unknown"


def test_long_rule_bounded_substring_not_prefix_of_word() -> None:
    rules: dict[str, CategoryRule] = {"target": {"category": "Shopping", "subcategory": "Shopping"}}
    match = categorizer.find_best_rule_match("Targeting Solutions Inc", rules, threshold=0.99)
    assert match["match_type"] != "exact"


def test_target_store_still_exact_match() -> None:
    rules: dict[str, CategoryRule] = {"target": {"category": "Shopping", "subcategory": "Shopping"}}
    match = categorizer.find_best_rule_match("Target Store 123", rules, threshold=0.5)
    assert match["match_type"] == "exact"
    assert match["category"] == "Shopping"
