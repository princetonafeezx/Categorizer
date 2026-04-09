# Enable postponed evaluation of type annotations for forward references
from __future__ import annotations

# Import standard library modules for file handling, data structures, and CSV parsing
import csv
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

# Import internal modules for logic, parsing, schemas, and storage
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

# Define ANSI escape sequences for colorized terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"

# Set of standard categories to ensure data consistency and prevent typos
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

# Minimum length for a rule string to qualify for a substring match (prevents small words matching incorrectly)
_MIN_EXACT_SUBSTRING_CHARS = 4


def _bounded_phrase_in_text(haystack: str, needle: str) -> bool:
    """True if ``needle`` appears in ``haystack`` delimited by start/end or ASCII spaces."""
    # Immediately return False if needle is empty or not present at all
    if not needle or needle not in haystack:
        return False
    start = 0
    needle_len = len(needle)
    # Search through the haystack for occurrences of the needle
    while True:
        idx = haystack.find(needle, start)
        # If not found, break search
        if idx == -1:
            return False
        # Ensure there is a space or start of string before the match
        before_ok = idx == 0 or haystack[idx - 1] == " "
        after_idx = idx + needle_len
        # Ensure there is a space or end of string after the match
        after_ok = after_idx == len(haystack) or haystack[after_idx] == " "
        # If both boundaries are clean (tokens), it's a valid bounded phrase
        if before_ok and after_ok:
            return True
        # Otherwise, continue searching past the current match
        start = idx + 1

# Helper to check if the tokens of a rule appear in exact order within the merchant string
def _tokens_have_consecutive_phrase(merchant_tokens: list[str], rule: str) -> bool:
    # Split the rule into its own tokens
    rule_tokens = rule.split()
    # If rule is empty, no match
    if not rule_tokens:
        return False
    # If rule is a single word, check if it's in the merchant list
    if len(rule_tokens) == 1:
        return rule_tokens[0] in merchant_tokens
    m, r = len(merchant_tokens), len(rule_tokens)
    # If rule is longer than the merchant string, it can't be a sub-phrase
    if r > m:
        return False
    # Use a sliding window to check for the consecutive sequence of tokens
    for i in range(m - r + 1):
        if merchant_tokens[i : i + r] == rule_tokens:
            return True
    return False

# Logic to determine if a rule matches a merchant string exactly or via high-confidence heuristics
def _exact_rule_matches(merchant_key: str, normalized_rule: str) -> bool:
    # Rule must not be empty
    if not normalized_rule:
        return False
    # Absolute string equality
    if merchant_key == normalized_rule:
        return True
    # Token-based phrase matching
    merchant_tokens = merchant_key.split()
    if _tokens_have_consecutive_phrase(merchant_tokens, normalized_rule):
        return True
    # Calculate length without spaces for minimum character check
    compact_rule_len = len(normalized_rule.replace(" ", ""))
    if compact_rule_len < _MIN_EXACT_SUBSTRING_CHARS:
        return False
    # Bounded substring check (needle in haystack)
    if _bounded_phrase_in_text(merchant_key, normalized_rule):
        return True
    # Bounded substring check (reverse: haystack in needle)
    if _bounded_phrase_in_text(normalized_rule, merchant_key):
        return True
    return False

# Built-in dictionary of common merchant-to-category mappings
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
    """Read CSV rows and normalize them into transaction dictionaries."""
    transactions: list[dict[str, Any]] = []
    warnings: list[str] = []
    input_path = Path(file_path)
    # Ensure the file exists before attempting to open it
    if not input_path.exists():
        raise FileNotFoundError(f"Could not find file: {input_path}")

    # Open the CSV file with utf-8-sig to handle potential Byte Order Marks (BOM)
    with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            # Extract the first row as headers
            headers = next(reader)
        except StopIteration:
            return [], ["The file was empty."]

        # Automatically detect which columns contain date, merchant, and amount
        column_map = detect_columns(headers)
        needed_indexes = {column_map["date"], column_map["merchant"], column_map["amount"]}
        # If any essential column is missing, warn the user
        if None in needed_indexes:
            warnings.append("I could not confidently find every column, so some rows may be skipped.")

        # Process each row, keeping track of the line number for error reporting
        for line_number, row in enumerate(reader, start=2):
            # Skip empty rows or rows containing only whitespace
            if not row or not any(cell.strip() for cell in row):
                continue
            try:
                cd = column_map["date"]
                cm = column_map["merchant"]
                ca = column_map["amount"]
                # Ensure we have column assignments
                if cd is None or cm is None or ca is None:
                    raise ValueError("Row does not have enough columns")
                # Ensure the row actually has enough cells for the detected indices
                if max(cd, cm, ca) >= len(row):
                    raise ValueError("Row does not have enough columns")
                # Extract and clean values
                date_value = row[cd].strip()
                merchant_value = row[cm].strip()
                # Parse the amount string into a numerical format
                amount_value = parse_amount(row[ca])
                # Validate that essential identity data is present
                if not date_value or not merchant_value:
                    raise ValueError("Date or merchant was blank")
                # Append the normalized dictionary to our list
                transactions.append(
                    {
                        "date": date_value,
                        "merchant": merchant_value,
                        "amount": amount_value,
                    }
                )
            except (ValueError, TypeError) as error:
                # Log the specific line and error if processing fails for a single row
                warnings.append(f"Skipped line {line_number}: {error}")
    return transactions, warnings


def generate_mock_transactions() -> list[dict[str, Any]]:
    """Build a simple demo statement when the user has no CSV yet."""
    today = date.today()
    # List of realistic transactions including some typos (e.g., "Starbuks") for testing
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
    # Create mock transaction data spread over several days
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
    """Try exact-ish matching first, then fuzzy matching."""
    # Clean the input merchant string for comparison
    merchant_key = clean_text(merchant)
    best_key: str | None = None
    best_score = 0.0
    best_match_type = "unknown"

    # Iterate through all available rules
    for rule_key, payload in rules.items():
        normalized_rule = clean_text(rule_key)
        if not normalized_rule:
            continue
        # Attempt exact/bounded matching first (highest confidence)
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

        # Calculate fuzzy similarity ratio for the entire string
        candidate_scores = [similarity_ratio(merchant_key, normalized_rule)]
        # Also check similarity of individual words in the merchant string against the rule
        for word in merchant_key.split():
            candidate_scores.append(similarity_ratio(word, normalized_rule))
        # Take the best score from the entire string or component words
        score = max(candidate_scores)
        # Update best match if current rule scores higher
        if score > best_score:
            best_score = score
            best_key = rule_key
            best_match_type = "fuzzy"

    # If a rule passed the threshold during fuzzy matching, return it
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

    # Fallback for when no match is found
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
    """Categorize every transaction and return low-confidence items too."""
    # Use provided rules or fallback to defaults
    active_rules = rules or DEFAULT_RULES.copy()
    categorized: list[CategorizedRecord] = []
    flagged: list[CategorizedRecord] = []

    # Iterate through every transaction record
    for transaction in transactions:
        # Get the best matching category from the rule engine
        match = find_best_rule_match(str(transaction.get("merchant", "")), active_rules, threshold)
        category = match["category"]
        # If the category is invalid or unknown, set to 'Unknown'
        if category not in VALID_CATEGORIES:
            category = "Unknown"
        # Determine subcategory (default to category if subcategory is empty)
        sub_raw = str(match["subcategory"]).strip()
        subcategory = sub_raw if sub_raw else category
        # Ensure the amount is a float
        try:
            amount = float(transaction["amount"])
        except (KeyError, TypeError, ValueError):
            amount = 0.0
        # Build the final categorized record
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

        # Flag records for review if they are fuzzy with low confidence, or completely unknown
        if row["match_type"] == "fuzzy" and row["confidence"] < min(0.95, threshold + 0.10):
            flagged.append(row)
        elif row["match_type"] == "unknown":
            flagged.append(row)

    return categorized, flagged


def summarize_categories(
    records: list[dict[str, Any]] | Sequence[Mapping[str, Any]],
) -> list[CategorySummaryRow]:
    """Roll transaction data into category totals and counts."""
    summary: dict[str, dict[str, Any]] = {}
    # Aggregate counts and amounts by category
    for record in records:
        category = str(record.get("category", "Unknown"))
        try:
            amount = float(record.get("amount", 0.0))
        except (TypeError, ValueError):
            amount = 0.0
        # Initialize category entry if not seen yet
        if category not in summary:
            summary[category] = {"category": category, "total": 0.0, "count": 0}
        # Update totals
        summary[category]["total"] += amount
        summary[category]["count"] += 1

    # Convert dictionary to list and sort by descending amount, then category name
    rows = list(summary.values())
    rows.sort(key=lambda item: (-float(item["total"]), item["category"]))
    return cast(list[CategorySummaryRow], rows)


def print_rules(rules: dict[str, CategoryRule] | None = None) -> None:
    """Show the rule engine in a readable table."""
    active_rules = rules or DEFAULT_RULES
    # Print table header
    print(f"{BLUE}Merchant Rule{' ' * 18}Category{' ' * 12}Subcategory{RESET}")
    print("-" * 68)
    # Print each rule in a formatted row
    for merchant, payload in sorted(active_rules.items()):
        print(f"{merchant:<30}{payload['category']:<24}{payload['subcategory']}")


def print_summary(records: Sequence[Mapping[str, Any]], flagged: Sequence[Mapping[str, Any]]) -> None:
    """Display sorted summary lines and any transactions needing review."""
    # Print the aggregate spending report
    summary_rows = summarize_categories(records)
    print(f"{GREEN}Categorized Summary{RESET}")
    print("-" * 55)
    print(f"{'Category':<22}{'Count':>8}{'Total':>18}")
    print("-" * 55)
    for row in summary_rows:
        print(f"{row['category']:<22}{row['count']:>8}{format_money(row['total']):>18}")

    # If there are transactions that need manual review, print them in a separate table
    if flagged:
        print()
        print(f"{YELLOW}Low-confidence / review list{RESET}")
        print("-" * 80)
        print(f"{'Date':<12}{'Merchant':<28}{'Category':<18}{'Confidence':>10}")
        print("-" * 80)
        for item in flagged:
            confidence_text = f"{item['confidence'] * 100:>8.1f}%"
            # Truncate merchant name if too long for the table
            print(f"{item['date']:<12}{item['merchant'][:27]:<28}{item['category']:<18}{confidence_text:>10}")
    else:
        print()
        print(f"{GREEN}No low-confidence matches needed review.{RESET}")


def add_rule_interactively(rules: dict[str, CategoryRule]) -> None:
    """Let the user add a merchant rule during the menu loop."""
    # Prompt user for rule details
    merchant = input("Merchant name to match: ").strip()
    category = input("Category: ").strip()
    subcategory = input("Subcategory: ").strip()
    # Basic validation of inputs
    if not merchant:
        print(f"{RED}Merchant cannot be blank.{RESET}")
        return
    if category not in VALID_CATEGORIES:
        print(f"{RED}That category is not in the known category set.{RESET}")
        return
    # Use category as subcategory if subcategory was left blank
    if not subcategory:
        subcategory = category
    # Save the rule using a cleaned key
    rules[clean_text(merchant)] = {"category": category, "subcategory": subcategory}
    # Persist the changes to storage
    save_rules_overrides(rules, DEFAULT_RULES)
    print(f"{GREEN}Added rule for {merchant} (saved to data directory).{RESET}")


def run_classification(
    file_path: str | Path | None = None,
    use_mock: bool = False,
    threshold: float = 0.76,
    rules: dict[str, CategoryRule] | None = None,
) -> ClassificationResult:
    """Public helper for the unified CLI."""
    # Setup working ruleset and warning list
    active_rules: dict[str, CategoryRule] = (rules or DEFAULT_RULES).copy()
    warnings: list[str] = []

    # Determine data source: mock generation or file reading
    if use_mock:
        transactions = generate_mock_transactions()
    else:
        if file_path is None:
            raise ValueError("A file path is required unless mock mode is enabled.")
        transactions, warnings = read_transaction_file(file_path)

    # Perform the categorization logic
    categorized, flagged = categorize_transactions(transactions, active_rules, threshold)
    # Package and return all results in a typed dictionary
    return cast(
        ClassificationResult,
        {
            "records": categorized,
            "flagged": flagged,
            "warnings": warnings,
            "summary": summarize_categories(categorized),
            "rules": active_rules,
        },
    )


def menu() -> None:
    """Run the interactive interface."""
    # Load existing rules (merging built-ins with saved overrides)
    rules = load_merged_category_rules(DEFAULT_RULES)
    valid_choices = {"1", "2", "3", "4", "5"}
    last_result = None

    # Main application loop
    while True:
        print()
        print(f"{BLUE}ll_categorizer: Smart Expense Classifier{RESET}")
        print("1. Classify transactions from CSV")
        print("2. Classify built-in mock data")
        print("3. View rules")
        print("4. Add a rule")
        print("5. Quit")
        choice = input("Choose an option: ").strip()

        # Handle invalid inputs
        if choice not in valid_choices:
            print(f"{RED}Please choose one of the menu numbers.{RESET}")
            continue

        # Option 1: Process external CSV file
        if choice == "1":
            file_path = input("CSV path: ").strip()
            try:
                last_result = run_classification(file_path=file_path, rules=rules)
                # Display any issues encountered during CSV parsing
                for warning in last_result["warnings"]:
                    print(f"{YELLOW}{warning}{RESET}")
                print_summary(last_result["records"], last_result["flagged"])
            except (OSError, ValueError, UnicodeError, csv.Error) as error:
                print(f"{RED}Could not classify that file: {error}{RESET}")

        # Option 2: Run simulation with mock data
        elif choice == "2":
            last_result = run_classification(use_mock=True, rules=rules)
            print_summary(last_result["records"], last_result["flagged"])

        # Option 3: List all current mapping rules
        elif choice == "3":
            print_rules(rules)
            if last_result:
                print()
                print(f"Last run had {len(last_result['records'])} categorized transactions.")

        # Option 4: Create a new custom rule
        elif choice == "4":
            add_rule_interactively(rules)

        # Option 5: Exit application
        elif choice == "5":
            print("Exiting classifier.")
            break


def main() -> None:
    # Entry point that triggers the menu system
    menu()


# Standard Python entry point
if __name__ == "__main__":
    main()