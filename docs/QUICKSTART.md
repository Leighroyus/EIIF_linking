# Quick Start Guide

## 5-Minute Setup

### Step 1: Prepare Your Data

You need two files — one per dataset. Column names don't need to match; the config handles mapping.

**set_a.csv** (Dataset A)
```csv
PersonID,GivenName,MiddleName,Surname,DOB,Sex,Suburb
A001,John,Michael,Smith,19800115,M,Springfield
A002,Mary,Elizabeth,Johnson,19750322,F,Shelbyville
```

**set_b.csv** (Dataset B — different column names, that's fine)
```csv
FirstName,LastName,BirthDate,GenderCode
John,Smith,1980-01-15,M
Mary,Johnston,19750322,F
```

### Step 2: Create Configuration File

```bash
cp config/example_linkage.yml config/my_linkage.yml
```

Edit `config/my_linkage.yml` — at minimum, update file paths and field mappings:

```yaml
dataset_a:
  source_type: csv
  source:
    file_path: data/set_a.csv
  unique_id:
    strategy: named_field
    field_name: PersonID
  field_mapping:
    first_name:    GivenName
    last_name:     Surname
    middle_name:   MiddleName
    date_of_birth: DOB
    gender:        Sex
    address_town_or_suburb: Suburb
  optional_fields: [middle_name, gender, address_town_or_suburb]

dataset_b:
  source_type: csv
  source:
    file_path: data/set_b.csv
  unique_id:
    strategy: hash
    hash_columns: [first_name, last_name, date_of_birth]
    hash_algorithm: md5
  field_mapping:
    first_name:    FirstName
    last_name:     LastName
    date_of_birth: BirthDate
    gender:        GenderCode
  optional_fields: [middle_name, gender, address_town_or_suburb]

linkage:
  thresholds:
    total_weight_min: 20.0
    confidence_high:  30.0
    confidence_medium: 20.0
    jw_first_name_min: 0.75
    jw_last_name_min:  0.75

output:
  format: csv
  file_path: results/linkage_results.csv

duckdb:
  database_path: ":memory:"
```

### Step 3: Run Pipeline

```bash
eiif-link config/my_linkage.yml
```

### Step 4: View Results

Open `results/linkage_results.csv`, or query via Python:

```python
import pandas as pd

results = pd.read_csv("results/linkage_results.csv")
print(results[["a_id", "b_id", "total_weight", "confidence", "match_rank", "is_best_match"]].head(20))
```

---

## Alternative: Use the Streamlit GUI

No config file needed — configure everything through the browser:

```bash
streamlit run src/eiif_linking/app/main.py
```

Four tabs: **Dataset A** → **Dataset B** → **Linkage Settings** → **Run & Results**

Upload files, set field mappings, adjust thresholds, run, and download results — all interactively.

---

## No Existing Unique IDs?

Use hash-based ID generation — a deterministic ID derived from field values:

```yaml
unique_id:
  strategy: hash
  hash_columns: [first_name, last_name, date_of_birth]
  hash_algorithm: sha256
```

The same person will always get the same hash if their name/DOB matches, allowing stable linkage even without a source ID.

---

## Common Adjustments

### Getting too many false matches?

```yaml
thresholds:
  total_weight_min: 25.0    # raise from 20.0
  jw_first_name_min: 0.80   # raise from 0.75
```

### Not finding enough matches?

```yaml
thresholds:
  total_weight_min: 15.0    # lower from 20.0
  jw_first_name_min: 0.70   # lower from 0.75
blocking:
  fuzzy_name_min: 0.80      # lower from 0.85
```

### Want only the best B match per A record?

```yaml
thresholds:
  max_matches_per_a_record: 1
```

### Want all B matches regardless of count?

Leave `max_matches_per_a_record: null` (the default). Use `match_rank` and `is_best_match` in your output to identify the best match when needed.

---

## Understanding Output Columns

| Column | Meaning |
|--------|---------|
| `a_id` | Identifier from Dataset A |
| `b_id` | Matched identifier from Dataset B |
| `total_weight` | Log-odds score — higher means more confident |
| `confidence` | HIGH (≥30) / MEDIUM (≥20) / LOW (<20) |
| `match_rank` | 1 = best B match for this A record; 2 = next best; etc. |
| `is_best_match` | TRUE if `match_rank = 1` |
| `sim_first_name` | Jaro-Winkler similarity for first names (0–1) |
| `wgt_first_name` | Log-odds weight contributed by first name |

## Understanding Match Quality

Typical log-odds score ranges:
- **< 15**: Weak — possible coincidences, check manually
- **15–25**: Moderate — good matches when names are common
- **25–40**: Strong — high-confidence matches
- **> 40**: Very strong — near-exact matches

---

## Troubleshooting

### No matches found
- Check data quality: are names and DOBs populated in both datasets?
- DOB format must be parseable as 8-digit numeric (YYYYMMDD or YYYY-MM-DD)
- Try lowering `total_weight_min` to 15.0 and `fuzzy_name_min` to 0.80
- Confirm the two datasets actually share people

### Too many matches
- Raise `total_weight_min` (try 25–30)
- Ensure DOB is mapped correctly — DOB is very discriminating when present

---

**For complete configuration reference, see [REFERENCE.md](REFERENCE.md)**
