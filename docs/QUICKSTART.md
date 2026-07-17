# Quick Start Guide - Justice Data Linkage v2

## 5-Minute Setup

### Step 1: Prepare Your Data

You need two CSV files:

**input_a.csv** (reference/base set)
```
person_id,first_name,middle_name,surname,date_of_birth,gender,street_number,street_name,suburb,state
P001,John,Michael,Smith,1980-01-15,M,123,Main Street,Springfield,IL
P002,Mary,Elizabeth,Johnson,1975-03-22,F,456,Oak Avenue,Shelbyville,IL
```

**input_b.csv** (new/query set)
```
person_id,first_name,middle_name,surname,date_of_birth,gender,street_number,street_name,suburb,state
P101,John,M,Smith,1980-01-15,M,123,Main Street,Springfield,IL
P102,William,H,Taylor,1990-02-14,M,202,New Street,New Town,IL
```

### Step 2: Create Configuration File

Copy the template and customize:

```bash
cp config/example_linkage.yml config/my_linkage.yml
```

Edit `config/my_linkage.yml`:

```yaml
extract_labels:
  input_a: "reference_202401"
  input_b: "current_202407"

dataset:
  name: "my_data"
  
  input_a:
    unique_id:
      strategy: "named_field"
      field_name: "person_id"
  
  input_b:
    unique_id:
      strategy: "named_field"
      field_name: "person_id"
  
  field_mapping:
    unique_id: "person_id"
    first_name: "first_name"
    middle_name: "middle_name"
    surname: "surname"
    date_of_birth: "date_of_birth"
    gender: "gender"
    street_number: "street_number"
    street_name: "street_name"
    suburb: "suburb"
    state: "state"

paths:
  input_a_raw_csv: "data/input_a.csv"
  input_b_raw_csv: "data/input_b.csv"

thresholds:
  total_weight_accept_new: 31
  total_weight_accept_existing: 35
  jw_first_name_min: 0.75
  last_name_uniqueness_threshold: 10
  fuzzy_name_min: 0.85
  fuzzy_birth_dt_min: 0.85

blocking:
  alphabet_chunks:
    - AB
    - CD
    - EF
    - GH
    - IJ
    - KL
    - MN
    - OP
    - QR
    - ST
    - UV
    - WX
    - YZ

duckdb:
  database_path: ".duckdb/linkage.duckdb"

artifacts:
  output_dir: "artifacts/linkage"
  export_csv: true
```

### Step 3: Run Pipeline

```bash
python -m eii_flinking.pipeline --config config/my_linkage.yml --export
```

Expected output:
```
Pipeline completed successfully. Database: /path/to/.duckdb/linkage.duckdb
```

### Step 4: View Results

Query the results:

```python
import duckdb

# Open results database
conn = duckdb.connect(".duckdb/linkage.duckdb", read_only=True)

# Get all matched records (CLUSTER_ID groups together matches)
matched = conn.execute("""
    SELECT CLUSTER_ID, PERSON_ID, FIRST_NAME, LAST_NAME, BIRTH_DT, DATA_SOURCE
    FROM out.final_linkage_output
    ORDER BY CLUSTER_ID
""").fetch_df()

print(matched)

# Summary: how many clusters formed
summary = conn.execute("""
    SELECT COUNT(*) as total_records, 
           COUNT(DISTINCT CLUSTER_ID) as total_clusters
    FROM out.final_linkage_output
""").fetch_df()
print(summary)

# Check matches between input_a and input_b
cross_matched = conn.execute("""
    SELECT CLUSTER_ID, COUNT(*) as cnt,
           STRING_AGG(DISTINCT DATA_SOURCE, ', ') as sources
    FROM out.final_linkage_output
    GROUP BY CLUSTER_ID
    HAVING COUNT(DISTINCT DATA_SOURCE) > 1
""").fetch_df()
print(f"\nMatches between datasets: {len(cross_matched)}")
print(cross_matched)

conn.close()
```

### Step 5: Export Results (Optional)

CSV files exported to `artifacts/linkage/` including:
- `final_linkage_output.csv`: Main results
- `probabilities_new.csv`: Match probabilities
- `scores_new.csv`: Match scores
- `accepted_new.csv`: Filtered pairs

---

## Special Case: No Existing Unique IDs?

If your data doesn't have unique IDs, use **hash-based generation**:

```yaml
dataset:
  input_b:
    unique_id:
      strategy: "hash"
      hash_columns:
        - first_name
        - surname
        - date_of_birth
        - suburb
      algorithm: "sha256"
```

The system will generate unique IDs deterministically from these columns.

---

## Common Adjustments

### Getting too many false matches?

Increase thresholds in config:
```yaml
thresholds:
  total_weight_accept_new: 35  # Increase from 31
  total_weight_accept_existing: 37  # Increase from 35
```

### Not finding enough matches?

Decrease thresholds:
```yaml
thresholds:
  total_weight_accept_new: 25  # Decrease from 31
  fuzzy_name_min: 0.80  # Decrease from 0.85
```

### Having issues with common names?

Adjust surname filter:
```yaml
thresholds:
  last_name_uniqueness_threshold: 5  # Lower = less filtering
```

---

## Expected Output Format

Final linkage table columns:

| Field | Meaning |
|-------|---------|
| SLK | Soundex-like key (healthcare standard) |
| PERSON_ID | Original unique ID from input |
| BIRTH_DT | Birth date (YYYYMMDD format) |
| FIRST_NAME | First name |
| LAST_NAME | Surname |
| GENDER_CD | Gender (M/F/U) |
| CLUSTER_ID | **Consolidated ID - same ID = matched records** |
| CONFIDENCE_DUP | 1 if this record matched to others |
| AVG_MATCH_WEIGHT | Average match score (higher = more confident) |
| DATA_SOURCE | Which input this came from (input_a label or input_b label) |

---

## Understanding Match Quality

Match weight interpretation:
- **Weight < 20**: Likely non-matches, but accepted (usually due to shared rare names/addresses)
- **Weight 20-40**: Good matches (most matches in this range)
- **Weight 40-60**: High-confidence matches
- **Weight > 60**: Very high-confidence matches (usually exact or near-exact matches)

---

## Troubleshooting

### Error: "Table not found"
- Check CSV file paths in config are correct
- Ensure CSV files have expected columns

### Error: "DuckDB database locked"
- Delete `.duckdb/` folder and re-run
- Only one process should access database at a time

### No matches found (CLUSTER_ID all different)
- Thresholds too high - try lowering
- Data quality issues - check names/DOBs
- Datasets have no overlapping people - verify expected overlaps

### Too many matches (false positives)
- Thresholds too low - try raising
- Address information missing - matches may be over-confident
- Common names dominating - try raising uniqueness threshold

---

## Next Steps

1. **Try with your own data**: Update config with real CSVs
2. **Validate results**: Review sample matched records manually
3. **Tune thresholds**: Adjust if needed based on results
4. **Automate**: Integrate pipeline into daily/weekly jobs
5. **Monitor quality**: Track average match weights over time

---

## Sample Real-World Command

```bash
# Victoria Police example
python -m eii_flinking.pipeline \
    --config src/eii_flinking/config/victoria_police_example.yml \
    --export
```

---

**For more details, see V2_README.md**
