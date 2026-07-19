# EIIF Linking — Complete Reference

## Overview

EIIF Linking performs cross-dataset probabilistic record linkage: given two independent extracts (Set A and Set B), it identifies records that refer to the same person. Unlike deduplication, this is a directed A→B search — every record in A is matched against every viable candidate in B.

### Key Design Choices

| Aspect | Approach |
|--------|----------|
| **Input** | CSV, Excel, or database connection — configured independently per dataset |
| **Field mapping** | Config-driven: any source schema → standard pipeline fields |
| **Unique IDs** | Use existing source column, or hash-generate from field combinations |
| **Matching model** | Fellegi-Sunter log-odds (probabilistic) with Jaro-Winkler string similarity |
| **Blocking** | 4-rule alphabet-chunked blocking — recovers name changes and DOB variations |
| **Optional fields** | NULL = 0 weight (no evidence, no penalty) |
| **Output** | Ranked pairs per A record with total weight, confidence band, match rank |
| **Interfaces** | CLI, Python API, Streamlit GUI |

---

## Directory Structure

```
src/eiif_linking/
├── __init__.py
├── schema.py                 # Standard field list, REQUIRED_FIELDS, defaults
├── config.py                 # AppConfig dataclasses + load_config()
├── pipeline.py               # run_pipeline() / run_pipeline_from_dataframes() / main()
├── address_parser.py         # Address parsing + LGA lookup (uses data/suburb_lga.csv)
├── slk.py                    # Soundex-like key generation
├── duckdb/
│   └── connection.py         # DuckDB connection; creates lnk/wrk/out schemas
├── connectors/
│   ├── base.py               # BaseConnector + field mapping logic
│   ├── csv_connector.py
│   ├── excel_connector.py
│   ├── database_connector.py
│   └── factory.py            # get_connector() / load_dataset()
├── stages/
│   ├── ingest.py             # Normalise raw → lnk.dataset_a / lnk.dataset_b (calls address_parser)
│   ├── proportions.py        # Field frequency tables (lnk.prop_*)
│   ├── blocking.py           # Candidate pairs → wrk.candidate_pairs
│   ├── scoring.py            # Log-odds weights → wrk.scored_pairs
│   └── post_linkage.py       # Filter, rank → out.linkage_results
└── app/
    └── main.py               # Streamlit GUI (4 tabs)

data/
└── suburb_lga.csv            # Australian suburb → LGA mapping (15,000+ localities)
```

DuckDB schema layout:
- **`lnk`** — staging and normalised data (`lnk.stg_a`, `lnk.stg_b`, `lnk.dataset_a`, `lnk.dataset_b`, `lnk.prop_*`)
- **`wrk`** — intermediate working tables (`wrk.raw_candidates`, `wrk.candidate_pairs`, `wrk.scored_pairs`)
- **`out`** — final output (`out.linkage_results`)

---

## Configuration Reference

### Full Structure

```yaml
# ── Dataset A ─────────────────────────────────────────────────────────────────
dataset_a:
  source_type: csv           # csv | excel | database

  source:
    # CSV / Excel:
    file_path: data/set_a.csv
    sheet_name: Sheet1       # Excel only; omit for CSV
    encoding: utf-8          # CSV only (default utf-8)

    # Database (use instead of file_path):
    # connection_string: "postgresql://user:pass@host:5432/mydb"
    # table_name: people_set_a
    # query: "SELECT * FROM people WHERE extract_date = '2024-01-01'"

  unique_id:
    strategy: named_field    # named_field | hash

    # named_field — use an existing column as the ID:
    field_name: PersonID     # source column name (before field mapping)

    # hash — generate ID by hashing standard field values:
    # strategy: hash
    # hash_columns: [first_name, last_name, date_of_birth]
    # hash_algorithm: md5    # md5 | sha256

  field_mapping:
    # standard_field: source_column_name
    # Only list fields that exist in your source.
    first_name:    GivenName
    last_name:     Surname
    middle_name:   MiddleName
    date_of_birth: DOB
    gender:        Sex
    address_full:           FullAddress  # optional — auto-parsed into components
    address_street_number:  HouseNo      # optional — use if data is already split
    address_street_name:    StreetName   # optional
    address_town_or_suburb: Suburb       # optional
    address_lga:            LGA          # optional — auto-populated from suburb

  optional_fields:
    # Fields where NULL contributes 0 weight (no penalty).
    # List all non-required fields that may be absent or sparse.
    - middle_name
    - gender
    - address_full
    - address_street_number
    - address_street_name
    - address_town_or_suburb
    - address_lga

# ── Dataset B ─────────────────────────────────────────────────────────────────
dataset_b:
  # Same structure as dataset_a
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
    gender: GenderCode
    address_town_or_suburb: City
  optional_fields:
    - middle_name
    - gender
    - address_full
    - address_street_number
    - address_street_name
    - address_town_or_suburb
    - address_lga

# ── Linkage behaviour ─────────────────────────────────────────────────────────
linkage:
  thresholds:
    total_weight_min: 20.0       # minimum log-odds to include pair in output
    confidence_high:  30.0       # >= this → confidence = HIGH
    confidence_medium: 20.0      # >= this → confidence = MEDIUM; below → LOW
    jw_first_name_min: 0.75      # minimum Jaro-Winkler for first name
    jw_last_name_min:  0.75      # minimum Jaro-Winkler for last name
    max_matches_per_a_record: null  # null = all above threshold; 1 = best only

  blocking:
    fuzzy_name_min: 0.85         # Jaro-Winkler gate applied during blocking
    alphabet_chunks: [AB, CD, EF, GH, IJ, KL, MN, OP, QR, ST, UV, WXYZ]

  # Override default P(agree | same person) per field.
  # Defaults: first_name=0.90, last_name=0.92, date_of_birth=0.95,
  #           gender=0.98, middle_name=0.85,
  #           address_street_number=0.90, address_street_name=0.85,
  #           address_town_or_suburb=0.80, address_lga=0.75
  # match_probabilities:
  #   first_name: 0.88
  #   last_name:  0.90

# ── Output ────────────────────────────────────────────────────────────────────
output:
  format: csv              # csv | excel
  file_path: results/linkage_results.csv

# ── DuckDB ────────────────────────────────────────────────────────────────────
duckdb:
  database_path: ":memory:"   # use a file path to persist between runs
  # database_path: .duckdb/linkage.duckdb
```

### Standard Pipeline Fields

| Field | Required | Notes |
|-------|----------|-------|
| `first_name` | Yes | Normalised to uppercase, trimmed |
| `last_name` | Yes | Normalised to uppercase, trimmed |
| `middle_name` | No | Optional; often sparse |
| `date_of_birth` | No | YYYYMMDD format (hyphens stripped, validated by regex) |
| `gender` | No | Mapped to M / F / NULL |
| `address_full` | No | Free-text full address; auto-parsed into components if mapped |
| `address_street_number` | No | e.g. "42", "5A", "12/34" — exact-match scored |
| `address_street_name` | No | e.g. "HIGH STREET" — Jaro-Winkler fuzzy scored |
| `address_town_or_suburb` | No | Suburb or town — Jaro-Winkler fuzzy scored; also used for LGA lookup |
| `address_lga` | No | Local Government Area — auto-populated from suburb if absent; exact-match scored |

### Unique ID Strategies

**`named_field`** — uses an existing source column as the record ID:
```yaml
unique_id:
  strategy: named_field
  field_name: PersonID     # name of the column in the source file
```

**`hash`** — generates a deterministic ID from standard field values:
```yaml
unique_id:
  strategy: hash
  hash_columns: [first_name, last_name, date_of_birth]
  hash_algorithm: md5      # md5 | sha256
```
The hash is computed after field normalisation, so the same person will produce the same ID across extracts.

---

## Pipeline Stages

### Stage 1 — Ingest (`stages/ingest.py`)

Reads from the raw staging tables (`lnk.stg_a`, `lnk.stg_b`) populated by the connectors, normalises data, and writes to `lnk.dataset_a` and `lnk.dataset_b`.

Normalisation steps:
- **DOB**: strips hyphens, validates with `REGEXP_FULL_MATCH('[0-9]{8}')`, sets invalid to NULL
- **Names**: `UPPER(TRIM(...))`, empty string → NULL
- **Gender**: maps M/MALE/1 → `M`, F/FEMALE/2 → `F`, else → NULL

ID resolution:
- `named_field`: `CAST(source_column AS VARCHAR)`
- `hash/md5`: `md5(col1 || '|' || col2 || ...)`
- `hash/sha256`: `hex(sha256(...))`

### Stage 2 — Proportions (`stages/proportions.py`)

Builds a UNION ALL view of both datasets (`lnk.combined`) and calculates field value frequencies in `lnk.prop_{field}` tables for: `first_name`, `last_name`, `middle_name`, `date_of_birth`, `gender`.

These frequencies are used as the **UP** (unmatched probability) — the chance that two randomly chosen records share a value by coincidence. Rarer values produce stronger evidence when they agree.

Floor: `MIN_PROP = 0.0001` prevents division-by-zero on very rare values.

### Stage 3 — Blocking (`stages/blocking.py`)

Generates candidate pairs using 4 overlapping rules, then applies a Jaro-Winkler fuzzy gate to filter non-viable pairs.

**4 blocking rules:**

| Rule | Join Condition | Notes |
|------|---------------|-------|
| 1 | `LEFT(last_name,3)` equal + first initial equal | Alphabet-chunked by last_name |
| 2 | Exact `first_name` + exact `date_of_birth` | Allows surname change |
| 3 | Exact `last_name` + `LEFT(dob,6)` (year+month) | Allows day error |
| 4 | Exact `first_name` + exact `last_name` | No DOB required |

**Fuzzy gate** (applied after UNION of all rules):
- Rules 1 and 4: `jaro_winkler(first_name) >= fuzzy_name_min` AND `jaro_winkler(last_name) >= fuzzy_name_min`
- Rules 2 and 3 (DOB-anchored): use a relaxed threshold `max(0.60, fuzzy_name_min - 0.20)` to allow for surname changes

**Alphabet chunking**: Rule 1 processes last names in chunks (AB, CD, ..., WXYZ) — reduces peak memory without affecting recall.

Candidates written to `wrk.raw_candidates`, deduplicated → `wrk.candidate_pairs`.

### Stage 4 — Scoring (`stages/scoring.py`)

Calculates a log-odds weight for each field, then sums to `total_weight`.

**For string fields (first_name, last_name, middle_name):**
- JW ≥ 0.92 (full match): `log₂(MP / UP)` — full agreement weight
- JW ≥ 0.75 (partial match): linearly interpolated
- Below 0.75: `log₂((1-MP) / (1-UP))` — disagreement weight
- Either value NULL → 0.0

UP values for name fields are taken as `LEAST(freq_in_A, freq_in_B)` from the combined population frequency tables.

**For date of birth:**
- Exact match: `log₂(MP / UP)`
- JW ≥ 0.85: interpolated (allows transpositions/typos)
- Below 0.85: disagreement weight
- Either NULL → 0.0

**For gender:**
- Exact match (both M or both F): agreement weight
- Both present but different: disagreement weight
- Either NULL → 0.0

**For address fields (street_number, street_name, town_or_suburb, lga):**

Address fields use fixed UP values (not population frequency tables, because address distributions are geographically local — a globally-observed suburb frequency would over-weight common names like "NORTH SYDNEY").

| Field | Scoring method | UP | Match probability (default) |
|-------|---------------|----|-----------------------------|
| `address_street_number` | Exact match | 0.05 | 0.90 |
| `address_street_name` | Jaro-Winkler fuzzy | 0.01 | 0.85 |
| `address_town_or_suburb` | Jaro-Winkler fuzzy | 0.02 | 0.80 |
| `address_lga` | Exact match | 0.10 | 0.75 |

**Crucially, address mismatches always return 0.0 weight (not negative).** Address data quality is variable — people move, formatting varies, unit numbers conflict with street numbers — so disagreement is treated as "no evidence" rather than evidence against a match. Only agreement contributes to the total weight.

**Address auto-parsing:** The `address_parser` module is run during ingest. If `address_full` is mapped but the component fields (`address_street_number`, `address_street_name`, `address_town_or_suburb`) are absent, it parses the free-text address using regex. `address_lga` is auto-populated from `address_town_or_suburb` via the bundled `data/suburb_lga.csv` lookup (15,000+ Australian localities from 2016 ABS Census data).

### Stage 5 — Post-Linkage (`stages/post_linkage.py`)

Filters scored pairs and builds the final output table.

**Filters applied:**
1. `total_weight >= total_weight_min`
2. `sim_first_name >= jw_first_name_min`
3. `sim_last_name >= jw_last_name_min`

**Ranking:** Within each A record, pairs are ranked by `total_weight DESC`:
```sql
ROW_NUMBER() OVER (PARTITION BY a_id ORDER BY total_weight DESC) AS match_rank
```
`is_best_match = (match_rank = 1)`.

**QUALIFY clause:** When `max_matches_per_a_record` is set, a `QUALIFY match_rank <= N` clause limits output rows.

Results written to `out.linkage_results`.

---

## Output Schema

### `out.linkage_results`

| Column | Type | Description |
|--------|------|-------------|
| `a_id` | VARCHAR | Record identifier from Dataset A |
| `b_id` | VARCHAR | Record identifier from Dataset B |
| `total_weight` | DOUBLE | Sum of field-level log-odds weights |
| `confidence` | VARCHAR | HIGH / MEDIUM / LOW band |
| `match_rank` | INTEGER | 1 = best B match for this A record |
| `is_best_match` | BOOLEAN | TRUE if match_rank = 1 |
| `a_first_name` | VARCHAR | A record first name |
| `a_middle_name` | VARCHAR | A record middle name |
| `a_last_name` | VARCHAR | A record last name |
| `a_dob` | VARCHAR | A record date of birth (YYYYMMDD) |
| `a_gender` | VARCHAR | A record gender (M/F) |
| `a_street_number` | VARCHAR | A record street number |
| `a_street_name` | VARCHAR | A record street name |
| `a_town_or_suburb` | VARCHAR | A record suburb or town |
| `a_lga` | VARCHAR | A record Local Government Area |
| `b_first_name` ... `b_lga` | VARCHAR | B record equivalents |
| `sim_first_name` | DOUBLE | Jaro-Winkler similarity: first names (0–1) |
| `sim_last_name` | DOUBLE | Jaro-Winkler similarity: last names |
| `sim_middle_name` | DOUBLE | Jaro-Winkler similarity: middle names |
| `sim_dob` | DOUBLE | Jaro-Winkler similarity: dates of birth |
| `sim_street_name` | DOUBLE | Jaro-Winkler similarity: street names |
| `sim_town_or_suburb` | DOUBLE | Jaro-Winkler similarity: suburb/town |
| `wgt_first_name` | DOUBLE | Log-odds contribution: first name |
| `wgt_middle_name` | DOUBLE | Log-odds contribution: middle name |
| `wgt_last_name` | DOUBLE | Log-odds contribution: last name |
| `wgt_dob` | DOUBLE | Log-odds contribution: date of birth |
| `wgt_gender` | DOUBLE | Log-odds contribution: gender |
| `wgt_address_street_number` | DOUBLE | Log-odds contribution: street number |
| `wgt_address_street_name` | DOUBLE | Log-odds contribution: street name |
| `wgt_address_town_or_suburb` | DOUBLE | Log-odds contribution: suburb/town |
| `wgt_address_lga` | DOUBLE | Log-odds contribution: LGA |

---

## Algorithms

### Fellegi-Sunter Probabilistic Model

For each field, the weight is:
- **Agreement**: `w = log₂(MP / UP)`
- **Disagreement**: `w = log₂((1 - MP) / (1 - UP))`

Where:
- **MP** (match probability) = `P(field agrees | records are the same person)` — configured per field
- **UP** (unmatch probability) = `P(field agrees | records are different people)` — estimated from observed value frequency in the combined population

Total weight = sum of field weights. Higher weight → stronger evidence the pair is a true match.

### Jaro-Winkler Similarity

String similarity metric that weights prefix agreements more heavily. Range: 0 (completely different) to 1 (identical).

- `>= 0.92` → full agreement
- `>= 0.75` → partial agreement (interpolated weight)
- `< 0.75` → disagreement

### Soundex-Like Key (SLK)

`slk.py` implements the healthcare standard SLK-581, derived from surname (chars 2-4 phonetically encoded), first name (chars 1-3), DOB (YYYYMMDD), and gender (1/2/9). Available for downstream use via `from eiif_linking.slk import build_slk`.

---

## Interfaces

### CLI

```bash
eiif-link config/my_linkage.yml
eiif-link config/my_linkage.yml --no-export
```

### Python API

```python
from eiif_linking.pipeline import run_pipeline, run_pipeline_from_dataframes

# File-based (reads source files from config)
results_df = run_pipeline("config/my_linkage.yml")

# DataFrame-based (skip file I/O)
results_df = run_pipeline_from_dataframes(df_a, df_b, config)
```

Both return a `pandas.DataFrame` of `out.linkage_results`.

### Streamlit GUI

```bash
streamlit run src/eiif_linking/app/main.py
```

Tab 1 — **Dataset A**: drag-and-drop / Browse file uploader (CSV, xlsx, xls); auto-loads on selection; preview; unique ID strategy (named field selector or standard-field hash multiselect); field mapping selectboxes with auto-hint from column names

Tab 2 — **Dataset B**: same as Dataset A

Tab 3 — **Linkage Settings**: sliders for all thresholds (`total_weight_min`, `confidence_high`, `confidence_medium`, `jw_first_name_min`, `jw_last_name_min`, `fuzzy_name_min`); number input for `max_matches_per_a_record`

Tab 4 — **Run & Results**: runs `run_pipeline_from_dataframes()` with live progress; summary metrics showing matched/total counts for each dataset; then a **View** toggle with three modes:
- *Matched pairs* — all A→B pairs above threshold; filterable by confidence band, best-match-only checkbox, and minimum weight; CSV + Excel download
- *All Set A records* — every A record left-joined to its best B match; `matched` column flags linked vs unmatched rows; sorted matched-first
- *All Set B records* — same from B's perspective

---

## Threshold Tuning Guide

| Parameter | Lower value | Higher value | Default |
|-----------|-------------|--------------|---------|
| `total_weight_min` | More pairs (higher recall, more FP) | Fewer pairs (higher precision) | 20.0 |
| `jw_first_name_min` | More name variation allowed | Stricter | 0.75 |
| `jw_last_name_min` | As above for last name | Stricter | 0.75 |
| `fuzzy_name_min` | More candidates, higher recall | Fewer candidates, faster | 0.85 |

**Strict linkage (high-precision):**
```yaml
total_weight_min: 28.0
jw_first_name_min: 0.82
jw_last_name_min:  0.82
```

**Loose linkage (high-recall):**
```yaml
total_weight_min: 15.0
jw_first_name_min: 0.70
jw_last_name_min:  0.70
blocking:
  fuzzy_name_min: 0.78
```

---

## Troubleshooting

### No matches found
- Lower `total_weight_min` to 15.0 and `fuzzy_name_min` to 0.78
- Check DOB format (YYYYMMDD or YYYY-MM-DD)
- Verify datasets actually share people

### Too many false positives
- Raise `total_weight_min` to 25–30
- Ensure DOB is correctly mapped — it is the most discriminating field
- Raise `jw_first_name_min` / `jw_last_name_min`

### DuckDB errors
- If using a file path, delete the `.duckdb` file and rerun
- Only one process can write to a DuckDB file at a time

### Column not found errors
- Verify `field_mapping` values exactly match source column names
- Check for leading/trailing spaces: `df.columns.str.strip()`
