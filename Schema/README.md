# ll-categorizer

Rule-based **transaction categorizer** for bank-style CSV exports: infer **date / merchant / amount** columns, match merchants against keyword rules (exact token or phrase match, then fuzzy similarity), summarize spending by category, and flag low-confidence rows for review.

**Python:** 3.10+

## Install

From this directory:

```bash
pip install -e .
```

Editable install registers the modules on your environment’s `PYTHONPATH`, so you can run `import categorizer` (and the other modules) from any working directory.

With test and dev tools (recommended for contributors):

```bash
pip install -e ".[dev]"
```

Alternatively, install dependencies from the flat list (e.g. CI):

```bash
pip install -r requirements.txt
pip install -e .
```

Runtime dependencies are also listed under `[project]` / `[project.optional-dependencies]` in `pyproject.toml`.

## CLI

After install:

```bash
ll-categorizer
```

This starts the interactive menu (classify CSV, mock data, view rules, add rules). Custom rules are merged with the built-in defaults and persisted under your data directory as `rules_overrides.json` (only entries that differ from defaults are stored).

## Environment and data directory

| Variable | Purpose |
|----------|---------|
| `LL_CATEGORIZER_DATA_DIR` | Override the data directory (default: `./ll_categorizer_data` under the current working directory). |

Typical files under that directory:

- `rules_overrides.json` — custom merchant rules (merged over built-ins)
- `categorized_transactions.csv` — optional output from `storage.save_categorized_transactions`
- `categorizer_report.txt` — optional text report from `storage.write_text_report`

If you used an older build that wrote to `./ledgerlogic_data` or `LEDGERLOGIC_DATA_DIR`, move those files into the new location or set `LL_CATEGORIZER_DATA_DIR` to the old folder.

## Run tests

```bash
pytest
```

`pyproject.toml` sets `pythonpath = ["."]` for pytest, so tests run correctly from the repo root even before install (if dependencies are present).

### Lint and types (optional)

With `[dev]` installed:

```bash
black --check .
flake8 .
mypy categorizer.py storage.py Schema csv_columns.py parsing.py textutil.py
```

## Library usage

**Basic** (built-in rules only):

```python
from categorizer import run_classification

result = run_classification(file_path="statement.csv")
records = result["records"]
flagged = result["flagged"]
```

**With saved CLI-style overrides** (`rules_overrides.json` in your data directory):

```python
from categorizer import DEFAULT_RULES, run_classification
from storage import load_merged_category_rules

rules = load_merged_category_rules(DEFAULT_RULES)
result = run_classification(file_path="statement.csv", rules=rules)
```

Data directory helpers and CSV persistence live in `storage.py`.

## Heuristics (limitations)

- **Column detection** scores headers against keyword lists, picks a one-to-one mapping that maximizes total score, and **clears** a role if that column’s score stays below an internal threshold—so odd exports may yield `None` for some roles (and row skips plus warnings).
- **Exact rules** require whole-token or multi-token phrase matches, or **bounded** substring matches for rules with at least four non-space characters, so very short keys are not matched inside unrelated words.
- **Fuzzy** matching still uses edit distance / similarity; tune `threshold` in `find_best_rule_match` / `categorize_transactions` if you see borderline cases.

## Layout

Sources are primarily top-level modules (`categorizer.py`, `csv_columns.py`, `parsing.py`, etc.) packaged via `pyproject.toml` `py-modules`.

Typed contracts now live in the `Schema/` package with two focused modules: `rules.py` and `records.py`.
