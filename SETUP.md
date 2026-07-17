# EIIF Linking — Setup Guide

## Prerequisites

- Python 3.12 or later
- pip

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/Leighroyus/EIIF_linking.git
cd EIIF_linking
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

Or with conda:
```bash
conda create -n eii-flinking python=3.12
conda activate eii-flinking
```

### 3. Install Package and Dependencies

```bash
pip install -e .
```

This installs the `eii-link` CLI and all required dependencies:
- `duckdb >= 1.1.0`
- `pandas >= 2.2.0`
- `openpyxl >= 3.1.0` (Excel support)
- `xlrd >= 2.0.1` (legacy `.xls` support)
- `pyyaml >= 6.0`
- `sqlalchemy >= 2.0.0` (database connectors)
- `streamlit >= 1.36.0` (GUI)
- `plotly >= 5.22.0` (GUI charts)
- `pyarrow >= 16.0.0`

### 4. Verify Installation

```bash
eii-link --help
```

## Project Structure

```
EIIFlinking/
├── config/
│   └── example_linkage.yml       # Annotated configuration template
├── docs/                         # Documentation
├── src/
│   └── eii_flinking/
│       ├── __init__.py
│       ├── schema.py             # Standard field list and defaults
│       ├── config.py             # YAML → dataclass configuration loading
│       ├── pipeline.py           # Pipeline orchestration and entry points
│       ├── slk.py                # Soundex-like key generation
│       ├── duckdb/
│       │   └── connection.py     # DuckDB connection with lnk/wrk/out schemas
│       ├── connectors/           # Input source adapters
│       │   ├── base.py           # Abstract base + field mapping logic
│       │   ├── csv_connector.py
│       │   ├── excel_connector.py
│       │   ├── database_connector.py
│       │   └── factory.py
│       ├── stages/               # Pipeline stages (called in order by pipeline.py)
│       │   ├── ingest.py         # Normalise raw → lnk.dataset_a / lnk.dataset_b
│       │   ├── proportions.py    # Field frequency tables for UP calculation
│       │   ├── blocking.py       # Candidate pair generation (4 rules)
│       │   ├── scoring.py        # Log-odds weight calculation
│       │   └── post_linkage.py   # Ranking, filtering → out.linkage_results
│       └── app/
│           └── main.py           # Streamlit GUI
├── pyproject.toml
├── README.md
└── SETUP.md
```

## Configuration

Copy and adapt the example config:

```bash
cp config/example_linkage.yml config/my_linkage.yml
```

### Dataset configuration

Each dataset (`dataset_a` / `dataset_b`) specifies its source, ID strategy, and field mapping independently:

```yaml
dataset_a:
  source_type: csv           # csv | excel | database

  source:
    file_path: data/set_a.csv
    # sheet_name: Sheet1                      # Excel only
    # connection_string: "postgresql://..."   # database
    # table_name: people_set_a               # database
    # query: "SELECT * FROM people"          # database (alternative to table_name)

  unique_id:
    strategy: named_field    # named_field | hash
    field_name: PersonID     # source column name (named_field strategy)
    # hash_columns: [first_name, last_name, date_of_birth]  # hash strategy
    # hash_algorithm: md5    # md5 | sha256

  field_mapping:             # standard_field: source_column_name
    first_name:    GivenName
    last_name:     Surname
    date_of_birth: DOB
    gender:        Sex
    address_suburb: City     # optional — omit if not present

  optional_fields:           # NULL values in these fields won't penalise scores
    - middle_name
    - gender
    - address_suburb
    - address_line1
    - address_state
    - postcode
```

Standard pipeline fields: `first_name`, `last_name`, `middle_name`, `date_of_birth`, `gender`, `address_line1`, `address_suburb`, `address_state`, `postcode`. Only `first_name` and `last_name` are required; all others should be listed in `optional_fields` if they may be sparse.

### Linkage settings

```yaml
linkage:
  thresholds:
    total_weight_min: 20.0       # minimum log-odds to include a pair in output
    confidence_high:  30.0       # above this → HIGH confidence
    confidence_medium: 20.0      # above this → MEDIUM (below → LOW)
    jw_first_name_min: 0.75      # minimum Jaro-Winkler for first name
    jw_last_name_min:  0.75      # minimum Jaro-Winkler for last name
    max_matches_per_a_record: null  # null = all above threshold; 1 = best only

  blocking:
    fuzzy_name_min: 0.85         # Jaro-Winkler gate applied during blocking
    alphabet_chunks: [AB, CD, EF, GH, IJ, KL, MN, OP, QR, ST, UV, WXYZ]
```

### Output and DuckDB

```yaml
output:
  format: csv                    # csv | excel
  file_path: results/linkage_results.csv

duckdb:
  database_path: ":memory:"      # or a file path to persist the database
```

## Running the Pipeline

### CLI

```bash
eii-link config/my_linkage.yml
```

To skip file export (results still available in DuckDB):
```bash
eii-link config/my_linkage.yml --no-export
```

### Streamlit GUI

No config file required — configure everything through the UI:

```bash
streamlit run src/eii_flinking/app/main.py
```

Four tabs: Dataset A → Dataset B → Linkage Settings → Run & Results. Results can be downloaded as CSV or Excel directly from the browser.

### Python API

```python
from eii_flinking.pipeline import run_pipeline

# Returns a pandas DataFrame of results
results_df = run_pipeline("config/my_linkage.yml")
print(results_df.head())
```

For programmatic use with in-memory DataFrames (e.g., when data is already loaded):

```python
from eii_flinking.pipeline import run_pipeline_from_dataframes
from eii_flinking.config import load_config

config = load_config("config/my_linkage.yml")
results_df = run_pipeline_from_dataframes(df_a, df_b, config)
```

## Accessing Results

Results are written to `out.linkage_results` in the DuckDB connection. If `output.file_path` is set (and `--no-export` is not passed), they are also exported to that path.

### Query via Python

```python
import duckdb

conn = duckdb.connect("path/to/linkage.duckdb", read_only=True)

results = conn.execute("""
    SELECT a_id, b_id, total_weight, confidence, match_rank, is_best_match,
           a_first_name, a_last_name, b_first_name, b_last_name
    FROM out.linkage_results
    ORDER BY a_id, match_rank
""").fetch_df()

print(results)
conn.close()
```

### Output Columns

| Column | Type | Description |
|--------|------|-------------|
| `a_id` | VARCHAR | Record ID from Dataset A |
| `b_id` | VARCHAR | Record ID from Dataset B |
| `total_weight` | DOUBLE | Total log-odds match score |
| `confidence` | VARCHAR | HIGH / MEDIUM / LOW |
| `match_rank` | INTEGER | Rank within A record's matches (1 = best) |
| `is_best_match` | BOOLEAN | TRUE if match_rank = 1 |
| `a_first_name` | VARCHAR | A record first name |
| `a_middle_name` | VARCHAR | A record middle name |
| `a_last_name` | VARCHAR | A record last name |
| `a_dob` | VARCHAR | A record date of birth (YYYYMMDD) |
| `a_gender` | VARCHAR | A record gender (M/F) |
| `a_suburb` | VARCHAR | A record address suburb |
| `a_state` | VARCHAR | A record address state |
| `b_first_name` ... `b_state` | VARCHAR | B record equivalents |
| `sim_first_name` | DOUBLE | Jaro-Winkler similarity for first name (0–1) |
| `sim_last_name` | DOUBLE | Jaro-Winkler similarity for last name |
| `sim_middle_name` | DOUBLE | Jaro-Winkler similarity for middle name |
| `sim_dob` | DOUBLE | Jaro-Winkler similarity for date of birth |
| `wgt_first_name` | DOUBLE | Log-odds weight from first name field |
| `wgt_middle_name` | DOUBLE | Log-odds weight from middle name field |
| `wgt_last_name` | DOUBLE | Log-odds weight from last name field |
| `wgt_dob` | DOUBLE | Log-odds weight from date of birth field |
| `wgt_gender` | DOUBLE | Log-odds weight from gender field |
| `wgt_suburb` | DOUBLE | Log-odds weight from suburb field |

## Troubleshooting

### `eii-link: command not found`
The package was not installed. Run `pip install -e .` and ensure the virtual environment is activated.

### `FileNotFoundError` for CSV/Excel
Check that file paths in the config are correct relative to the directory where you run `eii-link`. Use absolute paths if unsure.

### Column mapping errors
Verify `field_mapping` values match actual column names. Print them with:
```python
import pandas as pd
print(pd.read_csv("data/set_a.csv").columns.tolist())
```

### No matches found
- Lower `total_weight_min` (try 15.0)
- Lower `jw_first_name_min` / `jw_last_name_min` (try 0.70)
- Lower `fuzzy_name_min` (try 0.80)
- Check DOB format: must be recognisable as 8-digit numeric (YYYYMMDD or YYYY-MM-DD)
- Verify the two datasets actually have overlapping people

### Too many false positives
- Raise `total_weight_min` (try 25–30)
- Raise `jw_first_name_min` / `jw_last_name_min`

## Documentation

- [README.md](README.md) — Project overview and quick start
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — 5-minute guide
- [docs/REFERENCE.md](docs/REFERENCE.md) — Complete configuration and algorithm reference
- [docs/IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) — Architecture details

---

Last Updated: 2026-07-17
