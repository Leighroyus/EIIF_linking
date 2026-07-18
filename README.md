# EIIF Linking — Cross-Dataset Record Linkage

Probabilistic record linkage between two independent extracts (Set A → Set B). Identifies the same person appearing in both datasets using configurable field mapping, Fellegi-Sunter log-odds scoring, and 4-rule alphabet-chunked blocking.

## Features

- **Cross-dataset A→B matching** — finds the same person in two independent extracts (not self-deduplication)
- **Flexible inputs** — CSV, Excel, or database connection for each dataset independently
- **Config-driven field mapping** — map any source column schema to standard pipeline fields via YAML
- **Optional fields** — NULL values contribute 0 weight (no penalty), never disqualify a pair
- **Probabilistic scoring** — Fellegi-Sunter log-odds model with Jaro-Winkler string similarity
- **Ranked output** — all pairs above threshold with `match_rank`, `is_best_match`, and confidence band (HIGH/MEDIUM/LOW)
- **Streamlit GUI** — drag-and-drop file loading, field mapping, threshold tuning, matched-pairs results, and full A/B coverage views showing unmatched records

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp config/example_linkage.yml config/my_linkage.yml
# Edit file paths, field mappings, and thresholds
```

### 3. Run

```bash
eiif-link config/my_linkage.yml
```

### 4. View Results

```python
import pandas as pd
results = pd.read_csv("results/linkage_results.csv")
print(results[["a_id", "b_id", "total_weight", "confidence", "match_rank"]].head())
```

Or use the interactive GUI:

```bash
streamlit run src/eiif_linking/app/main.py
```

## Directory Structure

```
EIIFlinking/
├── config/
│   └── example_linkage.yml       # Annotated configuration template
├── docs/                         # Documentation
├── src/eiif_linking/
│   ├── schema.py                 # Standard field definitions and defaults
│   ├── config.py                 # YAML → dataclass configuration loading
│   ├── pipeline.py               # Pipeline entry points (CLI + Python API)
│   ├── slk.py                    # Soundex-like key generation
│   ├── duckdb/
│   │   └── connection.py         # DuckDB with lnk/wrk/out schemas
│   ├── connectors/               # Input source adapters
│   │   ├── base.py               # Abstract base + field mapping logic
│   │   ├── csv_connector.py
│   │   ├── excel_connector.py
│   │   ├── database_connector.py
│   │   └── factory.py
│   ├── stages/                   # Pipeline stages
│   │   ├── ingest.py             # Normalise raw data → lnk.dataset_a/b
│   │   ├── proportions.py        # Field frequency tables (UP calculation)
│   │   ├── blocking.py           # Candidate pair generation (4 rules)
│   │   ├── scoring.py            # Log-odds weight calculation
│   │   └── post_linkage.py       # Ranking, filtering, output
│   └── app/
│       └── main.py               # Streamlit GUI
└── pyproject.toml
```

## Configuration

Key structure (full reference in [`config/example_linkage.yml`](config/example_linkage.yml)):

```yaml
dataset_a:
  source_type: csv           # csv | excel | database
  source:
    file_path: data/set_a.csv
  unique_id:
    strategy: named_field    # or hash
    field_name: PersonID     # source column used as ID
  field_mapping:
    first_name: GivenName    # standard_field: source_column_name
    last_name:  Surname
    date_of_birth: DOB
    gender: Sex
  optional_fields: [middle_name, gender, address_suburb]

dataset_b:
  source_type: excel
  source:
    file_path: data/set_b.xlsx
    sheet_name: People
  unique_id:
    strategy: hash
    hash_columns: [first_name, last_name, date_of_birth]
    hash_algorithm: md5
  field_mapping:
    first_name: FirstName
    last_name:  LastName
    date_of_birth: BirthDate

linkage:
  thresholds:
    total_weight_min: 20.0
    confidence_high:  30.0
    confidence_medium: 20.0
    jw_first_name_min: 0.75
    jw_last_name_min:  0.75
    max_matches_per_a_record: null  # null = all above threshold; 1 = best only

output:
  format: csv
  file_path: results/linkage_results.csv

duckdb:
  database_path: ":memory:"
```

## Output

Results written to `out.linkage_results` in DuckDB and optionally exported to CSV.

| Column | Description |
|--------|-------------|
| `a_id` | Record identifier from Dataset A |
| `b_id` | Record identifier from Dataset B |
| `total_weight` | Log-odds match score (higher = more confident) |
| `confidence` | HIGH / MEDIUM / LOW band label |
| `match_rank` | Rank of this B match for the given A record (1 = best) |
| `is_best_match` | TRUE if this is the top-ranked B match for this A record |
| `a_first_name`, `a_last_name`, `a_dob`, `a_gender`, `a_suburb`, `a_state` | A record fields |
| `b_first_name`, `b_last_name`, `b_dob`, `b_gender`, `b_suburb`, `b_state` | B record fields |
| `sim_first_name`, `sim_last_name`, `sim_middle_name`, `sim_dob` | Jaro-Winkler similarity scores |
| `wgt_first_name`, `wgt_last_name`, `wgt_dob`, `wgt_gender`, `wgt_suburb` | Field-level log-odds weights |

## Algorithms

### Fellegi-Sunter Probabilistic Matching
Each field contributes a log-odds weight: `log₂(MP / UP)` for agreement, `log₂((1-MP) / (1-UP))` for disagreement, where MP is the configured match probability and UP is the observed value frequency in the combined A+B population.

### 4-Rule Blocking
Four overlapping rules generate candidate pairs to recover surname-changed individuals:
1. Last-name prefix (first 3 chars) + first initial — alphabet-chunked by last name
2. Exact first name + exact date of birth
3. Exact last name + birth year-month
4. Exact first name + last name (no DOB required)

Jaro-Winkler fuzzy gates filter non-viable pairs before scoring.

### Optional Field Handling
NULL in either record → field weight = 0.0 (no evidence either way, no penalty). Configure per-dataset via `optional_fields`.

## CLI

```bash
eiif-link config/my_linkage.yml           # run pipeline and export results
eiif-link config/my_linkage.yml --no-export  # skip CSV export
```

## Python API

```python
from eiif_linking.pipeline import run_pipeline, run_pipeline_from_dataframes

# File-based — returns pandas DataFrame
results_df = run_pipeline("config/my_linkage.yml")

# DataFrame-based (for scripting / Streamlit backend)
results_df = run_pipeline_from_dataframes(df_a, df_b, config)
```

## Streamlit GUI

```bash
streamlit run src/eiif_linking/app/main.py
```

Four tabs: **Dataset A** → **Dataset B** → **Linkage Settings** → **Run & Results**

- **Dataset A / B tabs**: drag-and-drop or browse to upload a CSV or Excel file; configure unique ID strategy and field mapping
- **Linkage Settings**: sliders for all match thresholds
- **Run & Results**: runs the pipeline with live progress, shows summary metrics (matched/total per dataset), and offers three result views:
  - *Matched pairs* — all A→B links above threshold, with confidence/weight filters
  - *All Set A records* — every A record with its best B match where found; unmatched rows flagged
  - *All Set B records* — same from B's perspective
- CSV and Excel download buttons adapt to whichever view is active

## Configuration Thresholds

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `total_weight_min` | 20.0 | Minimum log-odds to include a pair in output |
| `confidence_high` | 30.0 | Total weight above which confidence = HIGH |
| `confidence_medium` | 20.0 | Total weight above which confidence = MEDIUM |
| `jw_first_name_min` | 0.75 | Minimum Jaro-Winkler similarity for first name |
| `jw_last_name_min` | 0.75 | Minimum Jaro-Winkler similarity for last name |
| `fuzzy_name_min` | 0.85 | Jaro-Winkler gate used during blocking |
| `max_matches_per_a_record` | null | Limit B matches per A record (null = unlimited) |

## Troubleshooting

### No matches found
- Lower `total_weight_min` (try 15.0)
- Lower `jw_first_name_min` / `jw_last_name_min` (try 0.70)
- Check DOB format (YYYYMMDD or YYYY-MM-DD)
- Verify datasets actually share people

### Too many false positives
- Raise `total_weight_min` (try 25–30)
- Raise fuzzy similarity thresholds

### Unique ID hash collisions
- Use `sha256` instead of `md5`
- Add more columns to `hash_columns`

## Documentation

- **[docs/QUICKSTART.md](docs/QUICKSTART.md)** — 5-minute setup guide
- **[docs/REFERENCE.md](docs/REFERENCE.md)** — complete configuration and algorithm reference
- **[docs/IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md)** — architecture overview
- **[docs/INDEX.md](docs/INDEX.md)** — documentation navigation guide

## License

[Specify your license]

---

**Status:** Production Ready  
**Last Updated:** 2026-07-17
