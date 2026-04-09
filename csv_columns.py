"""Infer CSV column indices for date, merchant, and amount from header row text."""

# Enable postponed evaluation of type annotations for compatibility with older Python 3 versions
from __future__ import annotations

# Import itertools to generate all possible permutations of column assignments
import itertools

# Import the clean_text helper from the project's textutil module to normalize header strings
from textutil import clean_text

# Define the minimum character length required for a keyword to be eligible for substring matching
_MIN_KEYWORD_SUBSTRING_LEN = 5
# Define the minimum confidence threshold required to assign a role to a column
_MIN_ROLE_SCORE = 0.4

# Define a tuple of keywords commonly used to identify a "date" column
_DATE_KEYWORDS = (
    "date",
    "posted",
    "day",
)
# Define a tuple of keywords commonly used to identify a "merchant" or description column
_MERCHANT_KEYWORDS = (
    "merchant",
    "description",
    "payee",
    "narrative",
    "memo",
    "details",
    "detail",
    "vendor",
    "counterparty",
)
# Define a tuple of keywords commonly used to identify an "amount" or transaction value column
_AMOUNT_KEYWORDS = (
    "amount",
    "debit",
    "credit",
    "value",
    "total",
    "price",
)

# Helper function to calculate a confidence score (0.0 to 1.0) for a specific header string against a set of keywords
def _score_header_for_role(header: str, keywords: tuple[str, ...]) -> float:
    # Normalize the header text (lowercase, remove special chars)
    h = clean_text(header)
    # If the header is empty after cleaning, it has zero similarity to any role
    if not h:
        return 0.0
    # Split the header into individual words (tokens)
    tokens = h.split()
    # Initialize the best score found so far
    best = 0.0
    # Iterate through each keyword in the provided tuple
    for kw in keywords:
        # Check for an exact match between the cleaned header and the keyword
        if h == kw:
            best = max(best, 1.0)
        # Check if the keyword exists as a standalone word within the header
        elif kw in tokens:
            best = max(best, 0.95)
        # Check if the header starts or ends with the keyword followed/preceded by a space
        elif h.startswith(kw + " ") or h.endswith(" " + kw):
            best = max(best, 0.9)
        # Check for a substring match if the keyword is long enough to avoid false positives
        elif len(kw) >= _MIN_KEYWORD_SUBSTRING_LEN and kw in h:
            best = max(best, 0.75)
    # Return the highest score achieved for this header/role combination
    return best


def detect_columns(headers: list[str]) -> dict[str, int | None]:
    """Map logical roles ``date``, ``merchant``, and ``amount`` to column indices.

    Chooses a one-to-one assignment that maximizes the sum of header-to-role scores.
    When fewer than three columns exist, assigns roles greedily to distinct indices.
    Returns all ``None`` when no column scores positively for the best assignment.
    """
    # Get the total number of columns in the CSV headers
    n = len(headers)
    # Initialize the default result dictionary with None for all required roles
    empty: dict[str, int | None] = {"date": None, "merchant": None, "amount": None}
    # If there are no headers provided, return the empty mapping immediately
    if n == 0:
        return empty.copy()

    # Pre-calculate the scores for every column against all three roles
    per_col: list[tuple[float, float, float]] = []
    for h in headers:
        per_col.append(
            (
                _score_header_for_role(h, _DATE_KEYWORDS),
                _score_header_for_role(h, _MERCHANT_KEYWORDS),
                _score_header_for_role(h, _AMOUNT_KEYWORDS),
            )
        )

    # Optimization path for CSVs with at least 3 columns (finding the best global fit)
    if n >= 3:
        # Track the highest cumulative score across all role assignments
        best_total = -1.0
        # Track the mapping that produced the best score
        best_mapping = empty.copy()
        # Iterate through every possible unique combination of 3 columns
        for cols in itertools.permutations(range(n), 3):
            # Unpack the current permutation into date, merchant, and amount indices
            d, m, a = cols
            # Sum the individual role scores for this specific column combination
            total = per_col[d][0] + per_col[m][1] + per_col[a][2]
            # If this combination is better than the previous best, update the records
            if total > best_total:
                best_total = total
                best_mapping = {"date": d, "merchant": m, "amount": a}
        # If no combination scored above zero, return the empty mapping
        if best_total <= 0.0:
            return empty.copy()
        # Define the fixed order of roles to validate their individual scores
        role_order = ("date", "merchant", "amount")
        # Ensure that each assigned column actually meets the minimum confidence threshold
        for key in role_order:
            idx = best_mapping[key]
            # Skip if no column was assigned to this role
            if idx is None:
                continue
            # Get the index (0, 1, or 2) corresponding to the role in the per_col scores
            role_idx = role_order.index(key)
            # If the specific column's score for this role is too low, reset it to None
            if per_col[idx][role_idx] < _MIN_ROLE_SCORE:
                best_mapping[key] = None
        # Return the finalized mapping for the 3+ column case
        return best_mapping

    # Fallback greedy logic for CSVs with fewer than 3 columns
    used: set[int] = set()
    # Create a copy of the empty result template
    result = empty.copy()
    # Define the keys to iterate through
    role_keys = ("date", "merchant", "amount")
    # For each role, find the best remaining column
    for role_idx, key in enumerate(role_keys):
        best_i: int | None = None
        best_s = -1.0
        # Check every column index
        for i in range(n):
            # Skip columns that have already been assigned to a previous role
            if i in used:
                continue
            # Retrieve the score for the current column and current role
            s = per_col[i][role_idx]
            # If this column is the best fit for the role so far, record it
            if s > best_s:
                best_s = s
                best_i = i
        # Assign the column to the role only if it meets the minimum score requirement
        if best_i is not None and best_s >= _MIN_ROLE_SCORE:
            result[key] = best_i
            # Mark this column index as used so it isn't assigned twice
            used.add(best_i)
    # Return the greedy mapping for the small-column-count case
    return result