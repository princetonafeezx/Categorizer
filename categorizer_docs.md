# Architecture Decision Record
## App 11 — Categorizer
**Ledger Logic Group | Document 1 of 5**
**Status: Accepted**

---

## Context

The Categorizer is the eleventh app in the portfolio and the fourth in the Ledger Logic group. It takes a CSV file of bank transactions and labels each row with a spending category (Food & Drink, Transportation, Shopping, etc.) and subcategory. Classification must handle real-world merchant names — misspellings, abbreviations, trailing qualifiers ("Amazon Marketplace", "Shell Oil"), and partial matches. The module outputs categorized records, a low-confidence review list, and a summary table.

---

## Decisions

### Decision 1 — Two-phase matching: exact first, fuzzy second

**Chosen:** `find_best_rule_match()` runs `_exact_rule_matches()` for every rule key before computing any fuzzy similarity. An exact match returns immediately with `confidence=1.0`. Only if no exact match is found does the function scan similarity ratios.

**Rejected:** Running fuzzy matching for all rules on every transaction.

**Reason:** Most transactions match known merchants exactly or via substring. Computing Levenshtein distance for 21+ default rules on every transaction is unnecessary when an exact or bounded match is available. The two-pass design is both more accurate (exact matches are unambiguous) and faster (early return avoids O(n²) comparisons for common cases).

---

### Decision 2 — `_exact_rule_matches()` with three tiers: equality, token phrase, bounded substring

**Chosen:** Three ordered checks: (1) full string equality, (2) token-sequence phrase match via `_tokens_have_consecutive_phrase()`, (3) bounded substring match via `_bounded_phrase_in_text()` (minimum 4 non-space characters).

**Rejected:** Simple `rule_key in merchant_key` substring check.

**Reason:** A plain substring check would match `"at"` inside `"Apartment Rental"`, `"net"` inside `"Netflix"`, and `"amazon"` inside `"amazon prime"` correctly — but would also match `"am"` inside any merchant name containing those letters. The bounded check requires the needle to start at a space boundary or string boundary, preventing short rule keys from producing false positives. The 4-character minimum in `_MIN_EXACT_SUBSTRING_CHARS` prevents `"cvs"` (3 chars) from matching via substring where it might collide with longer tokens.

---

### Decision 3 — `similarity_ratio()` checks whole string AND individual words

**Chosen:** `find_best_rule_match()` computes `similarity_ratio(merchant_key, normalized_rule)` for the full cleaned merchant string, plus `similarity_ratio(word, normalized_rule)` for each word in the merchant. Takes the max.

**Rejected:** Only comparing the whole merchant string.

**Reason:** "Netflixx" (typo) vs rule key "netflix": full-string ratio is `6/7 ≈ 0.86` which passes the threshold. But "Amazon Marketplace" vs "amazon": full-string ratio is `6/18 = 0.33` (fails) while individual word "amazon" vs "amazon" = `1.0` (passes). Per-word checking handles multi-word merchant names where only one word matches the rule key.

---

### Decision 4 — `detect_columns()` using `itertools.permutations` for global optimum

**Chosen:** `detect_columns()` in `csv_columns.py` scores all three roles (date, merchant, amount) against all headers using pre-calculated per-column scores. For ≥3 columns, it evaluates all `n! / (n-3)!` permutations and picks the assignment that maximizes the total score.

**Rejected:** Greedy per-role assignment (assign best date column, then best remaining merchant column, etc.).

**Reason:** Greedy assignment can produce suboptimal assignments. If a header `"posted amount"` scores 0.9 for date and 0.8 for amount, greedy assigns it to date first — but it might be better assigned to amount if there's a better date column at the same index. The permutation approach finds the globally optimal one-to-one assignment. For ≤3 columns, the greedy fallback is used (no permutation needed).

---

### Decision 5 — `textutil.py` as a separate shared module (`clean_text` + `similarity_ratio`)

**Chosen:** `textutil.py` contains `clean_text()` (lowercase + alphanumeric normalization) and `similarity_ratio()` (Levenshtein-based). Both `categorizer.py` and `csv_columns.py` import from `textutil`.

**Rejected:** Inlining string utilities in each file.

**Reason:** `clean_text()` must behave identically in the header-scoring context (`csv_columns.py`) and the merchant-matching context (`categorizer.py`). Separate implementations would drift. `similarity_ratio()` is a non-trivial function implementing the Levenshtein algorithm — it should be defined once and tested independently.

---

### Decision 6 — `load_merged_category_rules()` and `save_rules_overrides()` in `storage.py`

**Chosen:** User-added rules are stored in a separate overrides JSON file. `load_merged_category_rules(default_rules)` merges the defaults with user overrides at runtime. `save_rules_overrides()` writes only the non-default rules.

**Rejected:** Storing the full merged ruleset (including defaults) in the JSON file.

**Reason:** Storing defaults in the JSON means any update to `DEFAULT_RULES` in code would not be reflected for users who have run the app before — they would be pinned to the older default set. Storing only overrides means the full ruleset is always `DEFAULT_RULES + user_overrides`, and default updates are automatically picked up.

---

### Decision 7 — Mock transaction generator for demo mode

**Chosen:** `generate_mock_transactions()` produces 12 hardcoded transactions including intentional misspellings ("Starbuks", "Netflixx") spread over recent dates. Menu option 2 runs classification on this data.

**Rejected:** Requiring a CSV file for every run.

**Reason:** The mock generator makes the module immediately runnable without external data. "Starbuks" and "Netflixx" test the fuzzy matching path — they should be flagged as low-confidence matches and appear in the review list. This is the correct test of the module's core capability without needing real bank data.

---

## Consequences

**Positive:**
- Two-phase matching is accurate for real-world merchant names and avoids unnecessary Levenshtein computation.
- Global permutation assignment for column detection produces the best possible column mapping.
- Per-word fuzzy matching handles multi-word merchant names where only one word matches the rule.
- `textutil.py` as a shared module prevents normalization drift between column detection and merchant matching.
- Override-only persistence ensures default rule updates are always picked up.

**Negative / Trade-offs:**
- The permutation approach for `n` headers is O(n × n! / (n-3)!) — for a 20-column CSV it evaluates 6,840 permutations. For large CSVs with many columns this adds a small overhead at startup. In practice, transaction CSVs rarely have more than 10 columns.
- The fuzzy threshold (default 0.76) was chosen empirically. Merchants not in `DEFAULT_RULES` and not close to any rule key will be classified as "Unknown" regardless of how similar they look to a human. The threshold is a tunable parameter but is not exposed in the CLI.
- `VALID_CATEGORIES` is a hardcoded set. A user who adds a rule with a custom category outside this set will be rejected by `add_rule_interactively()`.

---

*Constitution reference: Articles 1, 2, 3. Amendment 1.3: `parsing.py`, `schemas.py`, `storage.py` are pinned snapshots.*


---


# Technical Design Document
## App 11 — Categorizer
**Ledger Logic Group | Document 2 of 5**

---

## Overview

The Categorizer reads a bank transaction CSV, auto-detects columns, applies a two-phase rule engine (exact then fuzzy) to classify each transaction, and outputs categorized records, a review list, and a summary. Rules are extensible via user overrides.

**Files:** `categorizer.py` (542 lines), `csv_columns.py` (column detection), `textutil.py` (string utilities)
**Shared (pinned snapshots):** `parsing.py`, `schemas.py`, `storage.py`
**Entry point:** `categorizer.main()` → `categorizer.menu()`
**Dependencies:** `csv`, `itertools`, `datetime`, `pathlib` (stdlib); `csv_columns`, `textutil`, `parsing`, `schemas`, `storage`

---

## Data Flow

```
Input: CSV file path or mock mode
        │
        ▼
read_transaction_file(file_path)
        ├─ csv.reader → headers
        ├─ detect_columns(headers) → {date: int, merchant: int, amount: int}
        └─ For each row:
               ├─ parse_amount(row[amount_col])
               └─ → {date, merchant, amount}
        │
        ▼
categorize_transactions(transactions, rules, threshold)
        │
        └─ For each transaction:
               find_best_rule_match(merchant, rules)
               ├─ Phase 1: _exact_rule_matches() per rule key
               │     ├─ Equality
               │     ├─ _tokens_have_consecutive_phrase()
               │     └─ _bounded_phrase_in_text() (min 4 chars)
               └─ Phase 2: similarity_ratio() (whole + per word)
                     └─ Best score ≥ threshold → fuzzy match
        │
        ▼
(categorized: list[CategorizedRecord], flagged: list[CategorizedRecord])
        │
        ▼
summarize_categories(categorized) → list[CategorySummaryRow]
        │
        ▼
ClassificationResult {records, flagged, warnings, summary, rules}
```

---

## `textutil.py`

### `clean_text(text: str) → str`
Lowercases input. Replaces all non-alphanumeric characters with spaces. Collapses multiple spaces. Result: lowercase alphanumeric words with single spaces.

Examples:
- `"Starbucks"` → `"starbucks"`
- `"at&t"` → `"at t"`
- `"Amazon Marketplace"` → `"amazon marketplace"`
- `"Shell Oil #4212"` → `"shell oil 4212"`

---

### `_levenshtein_distance(left, right) → int`
Classic dynamic-programming Levenshtein implementation. O(m × n) where m and n are string lengths. Returns the minimum number of single-character edits (insert, delete, replace).

---

### `similarity_ratio(left, right) → float`
1. Clean both strings via `clean_text()`
2. Both empty → `1.0`; one empty → `0.0`
3. Equal → `1.0`
4. One is a substring of the other → `len(shorter) / len(longer)`
5. Otherwise → `max(0.0, 1.0 - levenshtein_distance / max_len)`

The substring path handles "Amazon" matching "amazon marketplace" with ratio `6/18 = 0.33` — but in `find_best_rule_match()`, the per-word pass checks `similarity_ratio("amazon", "amazon") = 1.0`.

---

## `csv_columns.py`

### `_score_header_for_role(header, keywords) → float`
Score tiers:
- Exact match: 1.0
- Token match: 0.95
- Starts/ends with keyword + space: 0.90
- Substring (keyword ≥ 5 chars): 0.75
- No match: 0.0

### `detect_columns(headers) → dict[str, int | None]`
For ≥3 headers: evaluates all `itertools.permutations(range(n), 3)`, returns the assignment maximizing `score_date + score_merchant + score_amount`. Each assigned column must also individually meet `_MIN_ROLE_SCORE = 0.4`.

For <3 headers: greedy assignment — for each role, take the highest-scoring unused column ≥ 0.4.

Returns `{"date": int|None, "merchant": int|None, "amount": int|None}`.

---

## `categorizer.py` Key Functions

### `_bounded_phrase_in_text(haystack, needle) → bool`
Finds all occurrences of `needle` in `haystack`. Returns `True` only if a match is bounded by string start/end or ASCII space on both sides. Prevents `"net"` matching inside `"netflixx"` token.

### `_tokens_have_consecutive_phrase(merchant_tokens, rule) → bool`
Splits rule into tokens. For single-token rules: membership check. For multi-token rules: sliding window check over merchant token list.

### `_exact_rule_matches(merchant_key, normalized_rule) → bool`
Ordered checks: equality → token phrase → bounded substring (min 4 non-space chars in rule).

### `find_best_rule_match(merchant, rules, threshold=0.76) → RuleMatchResult`
Returns first exact match (confidence=1.0) or best fuzzy match ≥ threshold, or Unknown fallback.

### `categorize_transactions(transactions, rules, threshold) → tuple[list, list]`
Applies `find_best_rule_match()` to each transaction. Flags records where:
- `match_type == "fuzzy"` AND `confidence < min(0.95, threshold + 0.10)`
- OR `match_type == "unknown"`

### `summarize_categories(records) → list[CategorySummaryRow]`
Groups by `category`, sums `amount`, counts rows. Sorts by `(-total, category)`.

---

## Default Rules (21 entries)

| Rule Key | Category | Subcategory |
|---|---|---|
| starbucks | Food & Drink | Dining Out |
| whole foods | Food & Drink | Groceries |
| trader joe s | Food & Drink | Groceries |
| shell | Transportation | Transportation |
| chevron | Transportation | Transportation |
| uber | Transportation | Transportation |
| lyft | Transportation | Transportation |
| netflix | Entertainment | Entertainment |
| spotify | Entertainment | Entertainment |
| steam | Entertainment | Entertainment |
| amazon | Shopping | Shopping |
| target | Shopping | Shopping |
| walmart | Shopping | Shopping |
| cvs | Health | Health |
| walgreens | Health | Health |
| kaiser | Health | Insurance |
| comcast | Utilities | Utilities |
| pge | Utilities | Utilities |
| at&t | Utilities | Utilities |
| landlord | Housing | Rent |
| apartment | Housing | Rent |
| payroll | Income | Paycheck |

---

## `RuleMatchResult` Schema

```python
{
    "category": str,
    "subcategory": str,
    "confidence": float,        # 0.0–1.0
    "match_type": str,          # "exact" | "fuzzy" | "unknown"
    "rule_key": str,            # matching rule key, "" if unknown
}
```

---

## `ClassificationResult` Schema

```python
{
    "records": list[CategorizedRecord],
    "flagged": list[CategorizedRecord],
    "warnings": list[str],
    "summary": list[CategorySummaryRow],
    "rules": dict[str, CategoryRule],
}
```

---

## Valid Categories

`"Food & Drink"`, `"Transportation"`, `"Entertainment"`, `"Shopping"`, `"Utilities"`, `"Health"`, `"Housing"`, `"Income"`, `"Travel"`, `"Other"`, `"Unknown"`


---


# Interface Design Specification
## App 11 — Categorizer
**Ledger Logic Group | Document 3 of 5**

---

## Public API

### Primary Entry Point

```python
run_classification(
    file_path: str | Path | None = None,
    use_mock: bool = False,
    threshold: float = 0.76,
    rules: dict[str, CategoryRule] | None = None,
) -> ClassificationResult
```

**Parameters:**
- `file_path` — path to CSV file. Required unless `use_mock=True`.
- `use_mock` — use built-in demo transactions instead of a file.
- `threshold` — fuzzy match confidence threshold (0.0–1.0, default 0.76).
- `rules` — custom rule dict. If `None`, uses `DEFAULT_RULES`.

---

### Supporting Functions

```python
find_best_rule_match(merchant, rules, threshold=0.76) -> RuleMatchResult
categorize_transactions(transactions, rules, threshold) -> tuple[list, list]
summarize_categories(records) -> list[CategorySummaryRow]
read_transaction_file(file_path) -> tuple[list[dict], list[str]]
generate_mock_transactions() -> list[dict]
```

**From `csv_columns`:**
```python
detect_columns(headers: list[str]) -> dict[str, int | None]
```

**From `textutil`:**
```python
clean_text(text: str) -> str
similarity_ratio(left: str, right: str) -> float
```

---

### CLI Entry Point

```bash
python categorizer.py
```

Interactive menu loop.

---

## Input/Output Examples

### Run classification on a CSV
```python
result = run_classification("transactions.csv")
print(f"Categorized: {len(result['records'])}")
print(f"Flagged for review: {len(result['flagged'])}")
for warning in result["warnings"]:
    print(f"Warning: {warning}")
```

### Access categorized records
```python
for record in result["records"]:
    print(f"{record['date']} | {record['merchant']:25} | "
          f"{record['category']:15} | {record['confidence']:.0%}")
```

### Mock data run
```python
result = run_classification(use_mock=True)
# Returns 12 transactions including intentional misspellings
# "Starbuks" → fuzzy match "starbucks", confidence ~0.86 → flagged
# "Netflixx" → fuzzy match "netflix", confidence ~0.86 → flagged
```

### Rule matching examples
```python
from categorizer import find_best_rule_match, DEFAULT_RULES

# Exact match
r = find_best_rule_match("Starbucks", DEFAULT_RULES)
# r["category"]: "Food & Drink", r["match_type"]: "exact", r["confidence"]: 1.0

# Fuzzy match (typo)
r = find_best_rule_match("Starbuks", DEFAULT_RULES)
# r["category"]: "Food & Drink", r["match_type"]: "fuzzy", r["confidence"]: ~0.86

# Multi-word with qualifier
r = find_best_rule_match("Amazon Marketplace", DEFAULT_RULES)
# r["category"]: "Shopping", r["match_type"]: "exact", r["confidence"]: 1.0
# (per-word: "amazon" exact matches rule key "amazon")

# No match
r = find_best_rule_match("Some Unknown Merchant", DEFAULT_RULES)
# r["category"]: "Unknown", r["match_type"]: "unknown", r["confidence"]: low
```

### Column detection
```python
from csv_columns import detect_columns

detect_columns(["Transaction Date", "Merchant", "Amount"])
# {"date": 0, "merchant": 1, "amount": 2}

detect_columns(["debit", "posted", "description", "currency"])
# {"date": 1, "merchant": 2, "amount": 0}

detect_columns(["foo", "bar", "baz"])
# {"date": None, "merchant": None, "amount": None}
```

### Summary output format
```
Categorized Summary
-------------------------------------------------------
Category              Count             Total
-------------------------------------------------------
Housing                   1         $1,450.00
Food & Drink              3           $100.40
Shopping                  2           $103.88
Transportation            2            $71.33
Utilities                 1            $79.99
Health                    1            $18.32
Entertainment             2            $25.48

Low-confidence / review list
--------------------------------------------------------------------------------
Date        Merchant                    Category          Confidence
--------------------------------------------------------------------------------
2026-04-30  Starbuks                    Food & Drink           86.0%
2026-04-24  Netflixx                    Entertainment          86.0%
```

---

## CSV Format Requirements

The module auto-detects columns from headers. Recommended column names:
- **Date**: `date`, `posted`, `day`
- **Merchant**: `merchant`, `description`, `payee`, `narrative`, `memo`, `details`, `vendor`
- **Amount**: `amount`, `debit`, `credit`, `value`, `total`, `price`

Accepted amount formats: `14.73`, `$14.73`, `(14.73)` (accounting negative), `1,234.56`.

---

## Interactive CLI Menu

| Option | Action |
|---|---|
| 1 | Classify from CSV file path |
| 2 | Classify built-in mock data |
| 3 | View current rules |
| 4 | Add a new rule interactively |
| 5 | Quit |


---


# Runbook
## App 11 — Categorizer
**Ledger Logic Group | Document 4 of 5**

---

## Requirements

- Python 3.10 or later
- No third-party dependencies
- `csv_columns.py`, `textutil.py`, `parsing.py`, `schemas.py`, `storage.py` in same directory or `PYTHONPATH`
- `typing_extensions` for `schemas.py` (Python < 3.11)

---

## Installation

```bash
git clone https://github.com/PrincetonAfeez/ledger-logic
cd ledger-logic/categorizer
pip install typing_extensions   # Only if Python < 3.11
```

---

## Running the CLI

### Interactive menu
```bash
python categorizer.py
```

### Quick demo (no CSV required)
```
> python categorizer.py
2. Classify built-in mock data
[Categorized Summary and low-confidence list displayed]
```

---

## Using as a Library

### Classify a CSV file
```python
from categorizer import run_classification
from storage import save_categorized_transactions

result = run_classification("bank_export.csv")
save_categorized_transactions(result["records"])

print(f"Classified: {len(result['records'])} transactions")
print(f"Flagged: {len(result['flagged'])} for review")
```

### Custom rules
```python
from categorizer import run_classification
from schemas import CategoryRule

custom_rules = {
    "whole foods": {"category": "Food & Drink", "subcategory": "Groceries"},
    "planet fitness": {"category": "Health", "subcategory": "Fitness"},
}
result = run_classification("bank_export.csv", rules=custom_rules)
```

### Test a specific merchant
```python
from categorizer import find_best_rule_match, DEFAULT_RULES

match = find_best_rule_match("Shell Oil Station 4212", DEFAULT_RULES)
print(f"Category: {match['category']}")
print(f"Match type: {match['match_type']}")
print(f"Confidence: {match['confidence']:.1%}")
```

### Detect columns in a header row
```python
from csv_columns import detect_columns

mapping = detect_columns(["Date", "Description", "Debit Amount"])
print(mapping)  # {"date": 0, "merchant": 1, "amount": 2}
```

---

## Running Tests

No dedicated test file was uploaded for App 11. Manual verification using mock data:

```bash
python categorizer.py
# Select 2 (mock data)
# Confirm "Starbuks" and "Netflixx" appear in the low-confidence review list
# Confirm "Starbucks" and "Netflix" do NOT appear in the review list
# Confirm "Amazon Marketplace" is categorized as Shopping (exact word match)
# Confirm "Landlord Portal" is categorized as Housing/Rent
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'csv_columns'`
`csv_columns.py` and `textutil.py` must be in the same directory as `categorizer.py`.

### `I could not confidently find every column` warning
The CSV headers don't match any recognized column keywords. Check header names against: `date/posted/day`, `merchant/description/payee/narrative`, `amount/debit/credit`. Rename headers or add the column keyword to the score list.

### Merchant is classified as "Unknown" despite being close to a rule
The fuzzy threshold is 0.76. Check the similarity:
```python
from textutil import similarity_ratio, clean_text
print(similarity_ratio(clean_text("my merchant"), "rule key"))
```
If below 0.76, add an explicit rule via menu option 4.

### Custom category rejected by `add_rule_interactively()`
The category must be in `VALID_CATEGORIES`. Use one of: Food & Drink, Transportation, Entertainment, Shopping, Utilities, Health, Housing, Income, Travel, Other. Category names are case-sensitive.

### Transactions from prior runs mixed with new run
Each `run_classification()` call is stateless — it does not load prior results. Use `load_categorized_transactions()` from `storage.py` to access previously saved transactions.


---


# Lessons Learned
## App 11 — Categorizer
**Ledger Logic Group | Document 5 of 5**

---

## Why This Design Was Chosen

The two-phase matching design came from a specific failure in the first version. The initial implementation ran `similarity_ratio()` for every rule on every transaction. "Starbucks" scored 1.0 on "starbucks" — correct. But "Shell Oil" scored ~0.3 on "shell" (whole-string comparison), failing to match. Adding per-word comparison fixed it. But running full Levenshtein for all 21 rules × 12 transactions × 18 tokens per transaction was measurably slower and produced false positives from short rule keys matching against short words.

The two-phase fix — exact matching first, fuzzy only if exact fails — was the right solution: faster for common cases (exact matches), more accurate (avoids short-string false positives from Levenshtein), and cleaner to reason about.

The mock data "Starbuks" and "Netflixx" were added specifically to test that the review list works correctly. Writing the test case before fixing the matching logic made the expected behavior concrete and verifiable.

---

## What Was Intentionally Omitted

**Machine learning classification:** Using a trained classifier (e.g., scikit-learn Naive Bayes on merchant names) would be more accurate than Levenshtein-based fuzzy matching for novel merchant names. This was intentionally omitted — the module is a learning exercise in string algorithms and rule-based systems, not ML. The README acknowledges this.

**Debit vs credit direction:** The amount parser strips the sign (returns absolute value). Whether a transaction is a debit (expense) or credit (income) is not tracked. A real bank export has signed amounts; the current implementation treats all amounts as positive expenses. Supporting income transactions properly would require preserving the sign and routing negative-amount rows to the "Income" category.

**Multi-file processing:** `run_classification()` accepts one file or mock data. Processing multiple CSV exports from different accounts (checking, credit card, savings) in one session requires calling the function multiple times and merging results.

**Training the fuzzy threshold from data:** The threshold of 0.76 was chosen by testing against the mock data set. A larger labeled dataset could be used to find the threshold that maximizes F1 score for the exact/fuzzy/unknown classification. This is the correct data-driven approach that was not implemented.

---

## Biggest Weakness

The column detection `detect_columns()` function uses `itertools.permutations(range(n), 3)`. For a typical 4–6 column CSV this is 24–120 permutations — negligible. For an unusual CSV with 15 columns it is `15 × 14 × 13 = 2,730` permutations. For a 20-column CSV it is `6,840`. This is still fast (microseconds per permutation) but is O(n³) growth. A 100-column CSV (a wide enterprise export) would evaluate 970,200 permutations. For DataGuard's typical inputs this never matters; for unusually wide CSVs it would need to be capped or replaced with a heuristic.

The deeper limitation is that `detect_columns()` operates on header names only — it does not look at cell values to confirm the column type. A column named "description" that contains numeric values would still be assigned as the merchant column. A cell-sampling step (check if the first 5 non-empty values in the column parse as dates or amounts) would catch this.

---

## Scaling Considerations

**If the rule set grows to hundreds of rules:** The two-phase matching becomes more expensive because it checks every rule key for exact matches before falling through to fuzzy. A prefix-indexed lookup (group rules by first 3 characters of the cleaned key) would reduce exact-match candidates without changing the interface.

**If the transaction file grows to millions of rows:** `read_transaction_file()` accumulates all rows in memory. A streaming version that calls `categorize_transactions()` in batches and writes to `save_categorized_transactions()` incrementally would handle large files.

**If more categories are needed:** `VALID_CATEGORIES` is a hardcoded set. Moving it to a JSON file loaded alongside the rules would allow user-defined categories without code changes.

---

## What the Next Refactor Would Be

1. **Cell-type sampling in `detect_columns()`** — check the first 5 non-empty cells in each candidate column to confirm the detected role (date cells parse as dates, amount cells parse as numbers).
2. **Signed amount support** — preserve debit/credit sign and route credit transactions to "Income" automatically.
3. **Prefix-indexed exact matching** — group rule keys by first 3 normalized characters to reduce the number of exact-match checks for large rule sets.
4. **Configurable `VALID_CATEGORIES`** — load from JSON alongside user override rules.

---

## What This Project Taught

**Two-phase matching is more accurate and faster than pure fuzzy matching.** The exact-first approach is not a micro-optimization — it produces qualitatively different results. "Amazon Marketplace" matched via per-word exact matching (`"amazon"` == `"amazon"`) produces `confidence=1.0`. The same match via Levenshtein produces `similarity_ratio("amazon marketplace", "amazon") = 6/18 = 0.33` — a near-miss that would fail the threshold. The choice of algorithm determines which merchants can be matched, not just how fast the matching runs.

**Bounded substring matching prevents false positives from short rule keys.** `"cvs"` is 3 characters. Without the bounded check, `"cvs"` would match inside any merchant containing those letters as a substring — "discovery", "services", etc. The space-boundary requirement ensures that "cvs" only matches when it appears as a standalone token. This is the correct definition of a merchant name match.

**Global permutation assignment is worth the O(n³) cost for small n.** Column header detection is done once per file, not once per row. The cost is a fixed setup overhead, not a per-row cost. Getting the optimal column assignment is worth that overhead because a wrong assignment corrupts every row in the file.

---

*Constitution v2.0 checklist: This document satisfies Article 5 (trade-off documentation) for App 11.*
