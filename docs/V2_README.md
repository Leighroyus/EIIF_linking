# Justice Data Linkage v2 - Redesigned Record Linkage System

## Overview

This is a complete redesign of the Justice Data Linkage system, focusing on:
- **Flexible input handling**: Named field or hash-based unique identifiers
- **Simplified architecture**: Single bespoke probabilistic matching pipeline
- **Configurable field mapping**: Map any dataset schema to standard fields
- **Clear terminology**: input_A/input_B instead of current/previous

## Key Improvements Over v1

| Aspect | v1 | v2 |
|--------|----|----|
| **Terminology** | current/previous (temporal) | input_a/input_b (symmetric) |
| **Unique IDs** | Assumed existing | Named field OR hash-based |
| **Field mapping** | Hard-coded assumptions | Configurable per dataset |
| **Architecture** | Splink + Bespoke | Bespoke only |
| **Simplicity** | ~1000+ files (multi-impl) | ~50 files (single pipeline) |

## Directory Structure

```
src/eii_flinking/
├── __init__.py
├── config.py                    # Configuration loading and path resolution
├── slk.py                       # Soundex-like key generation
├── duckdb_connection.py         # DuckDB connection management
├── stages/                      # Pipeline stages
│   ├── __init__.py
│   ├── unique_id_mapping.py     # Generate or map unique IDs
│   ├── prepare_sources.py       # Load and normalize data
│   ├── new_person_identification.py  # Classify new vs existing
│   ├── proportions.py           # Calculate field frequencies
│   ├── probabilities.py         # Assign match probabilities
│   ├── blocking.py              # Generate candidate pairs
│   ├── scoring.py               # Calculate match weights
│   └── post_linkage.py          # Filter, cluster, assign IDs
├── pipelines/                   # Main pipeline orchestration
│   ├── __init__.py
│   └── linking_full.py          # Split new/existing pipeline
├── cli/                         # Command-line interfaces
│   ├── __init__.py
│   └── run_linking.py           # Main CLI entry point
└── config/                      # Configuration templates
    ├── linkage_template.yml     # Full template with all options
    ├── victoria_police_example.yml
    └── hash_based_example.yml
```

## Configuration

### Basic Structure

```yaml
extract_labels:
  input_a: "reference_202401"
  input_b: "current_202407"

dataset:
  name: "my_dataset"
  
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
    surname: "surname"
    date_of_birth: "dob"
    gender: "sex"
    # ... other fields

paths:
  input_a_raw_csv: "data/reference.csv"
  input_b_raw_csv: "data/current.csv"

thresholds:
  total_weight_min: 20.0
  jw_first_name_min: 0.75
  last_name_uniqueness_threshold: 10
  fuzzy_name_min: 0.85
  fuzzy_birth_dt_min: 0.85

blocking:
  alphabet_chunks:
    - AB
    - CD
    # ... etc

duckdb:
  database_path: ".duckdb/linkage.duckdb"

artifacts:
  output_dir: "artifacts/linkage"
  export_csv: true
```

### Unique ID Strategies

#### 1. Named Field (existing ID column)
```yaml
input_a:
  unique_id:
    strategy: "named_field"
    field_name: "person_id"
```

#### 2. Hash-Based (generate from columns)
```yaml
input_b:
  unique_id:
    strategy: "hash"
    hash_columns:
      - first_name
      - surname
      - date_of_birth
      - suburb
    algorithm: "sha256"  # or "md5"
```

## Usage

### Command Line

```bash
# Run with default config
python -m eii_flinking.pipeline

# Run with custom config
python -m eii_flinking.pipeline --config config/my_linkage.yml

# Export intermediate tables
python -m eii_flinking.pipeline --config config/my_linkage.yml --export
```

### Python API

```python
from eii_flinking.pipelines.linking_full import run_pipeline

db_path = run_pipeline("config/linkage.yml", export=True)
print(f"Database created at {db_path}")
```

## Pipeline Stages

### 1. unique_id_mapping.py
- **Input**: CSV file, ID strategy config
- **Output**: Table with `unique_id` column
- **Logic**: Apply named field mapping OR generate hash from specified columns

### 2. prepare_sources.py
- **Input**: Two CSV files with unique IDs, field mapping config
- **Output**: Working tables for both datasets
- **Logic**: Load, normalize, apply field mapping, create working tables

### 3. new_person_identification.py
- **Input**: Person records from both datasets
- **Output**: new_people, existing_people tables
- **Logic**: Use LEAP filter to classify and filter valid records

### 4. proportions.py
- **Input**: All valid person records
- **Output**: Field frequency distributions
- **Logic**: Calculate P(field_value) for all fields

### 5. probabilities.py
- **Input**: Field frequencies, person IDs
- **Output**: Probability tables for new and existing
- **Logic**: Assign U (unmatched) and M (matched) probabilities to records

### 6. blocking.py
- **Input**: Probability tables
- **Output**: Candidate pairs (blocked)
- **Logic**: Multi-strategy blocking with alphabet chunking
  - Exact match on name + DOB year
  - Prefix + gender + DOB year
  - Name + DOB day combinations
  - Fuzzy filtering based on Jaro-Winkler + uniqueness gates

### 7. scoring.py
- **Input**: Candidate pairs
- **Output**: Scored pairs with match weights
- **Logic**: Calculate log-odds weights using probabilistic model
  - Jaro-Winkler similarity for names
  - Field agreement evaluation
  - Total weight = sum of field weights

### 8. post_linkage.py
- **Input**: Scored pairs
- **Output**: Final linkage output
- **Logic**: 
  - Add address matching
  - Filter by thresholds (weight, JW similarity, DOB validity)
  - Mirror pairs for self-join (new/new)
  - Union-Find clustering
  - Assign consolidated IDs (CLUSTER_ID)
  - Generate SLK codes

## Output

### Final Linkage Table: `out.final_linkage_output`

```
SLK                 # Soundex-like key for deterministic linkage
PERSON_ID           # Original unique identifier
BIRTH_DT            # Birth date (YYYYMMDD)
FIRST_NAME          # First name
SECOND_NAME         # Middle/second name
LAST_NAME           # Surname
GENDER_CD           # Gender code
CLUSTER_ID          # Consolidated ID (matched records share same ID)
CONFIDENCE_DUP      # Confidence in duplicate (0/1)
AVG_MATCH_WEIGHT    # Average match weight across edges
ADDRESS_MATCH       # Address match flag (0/1)
MANUAL_MATCH        # Manual verification flag
DATA_SOURCE         # Which extract (input_a label or input_b label)
DATA_SOURCE_UPDATE  # Update source (if applicable)
```

### Optional CSV Exports

When `export_csv: true`, intermediate tables are saved:
- `new_people.csv` - Records identified as new
- `existing_people.csv` - Records identified as existing
- `probabilities_new.csv` - Probability assignments for new
- `probabilities_existing.csv` - Probability assignments for existing
- `blocks_new.csv` - Candidate pairs (new/new)
- `blocks_existing.csv` - Candidate pairs (new/existing)
- `scores_new.csv` - Scored new/new pairs
- `scores_existing.csv` - Scored new/existing pairs
- `accepted_new.csv` - Filtered new/new pairs
- `accepted_existing.csv` - Filtered new/existing pairs

## Testing

### Run Tests

```bash
# Run all v2 tests
pytest tests/v2/ -v

# Run specific test
pytest tests/v2/test_unique_id_mapping.py -v

# Run with coverage
pytest tests/v2/ --cov=justice_data_linkage.v2 -v
```

### Sample Data

Test fixtures in `tests/v2/conftest.py` provide:
- `sample_data_dir`: Directory with test CSVs
- `config_file`: Pre-configured test config

Example test:
```python
def test_pipeline_execution(config_file: Path) -> None:
    db_path = run_pipeline(config_file, export=False)
    assert db_path.exists()
```

## Configuration Thresholds

### total_weight_min (default: 31)
- Minimum log-odds weight to accept new/new match
- Lower = more liberal matching
- Range: ~0-100

### total_weight_min (default: 35)
- Minimum weight for new/existing matches
- Typically higher than new/new (more conservative)

### jw_first_name_min (default: 0.75)
- Quality gate: minimum Jaro-Winkler similarity for first name
- After filtering, all pairs must meet this
- Range: 0.0-1.0

### last_name_uniqueness_threshold (default: 10)
- Surname rarity gate: blocks common surnames from fuzzy matching
- Value is log₂(max_freq / actual_freq)
- Higher = filter more common surnames

### fuzzy_name_min (default: 0.85)
- Minimum string similarity for fuzzy blocking rules
- Used in Jaro-Winkler and Levenshtein comparisons

### fuzzy_birth_dt_min (default: 0.85)
- Minimum normalized Levenshtein similarity for birth dates
- Allows minor DOB variations while blocking very different dates

## Algorithms

### Soundex-Like Key (SLK)
Deterministic key for healthcare standard linkage:
- First character of surname + phonetic code
- First character of first name + phonetic code
- Full DOB (YYYYMMDD)
- Gender code (1=M, 2=F, 9=U)

Example: `SM0719800115M` for Smith, John, 1980-01-15, Male

### Fellegi-Sunter Probabilistic Matching
- Base model: P(match | field agreement)
- Weight = log₂(P(agree|match) / P(agree|nomatch))
- Total weight = sum of field weights
- Threshold acceptance when total weight exceeds configured value

### Union-Find Clustering
- Implements disjoint-set union for transitive closure
- Identifies connected components in match graph
- Assigns unique consolidated ID per component

### Multi-Strategy Blocking
1. **Exact blocking**: First name + Last name + DOB year
2. **Prefix blocking**: First name prefix + Last name prefix + Gender + DOB year
3. **DOB day blocking**: First name + DOB year + DOB day + Gender
4. **DOB month blocking**: First name + DOB day + DOB month + Gender
5. **DOB year/month blocking**: First name + DOB year + DOB month + Gender

Fuzzy filter applied to all: Jaro-Winkler ≥ 0.85 + Levenshtein ≥ 0.85

## Performance Notes

- **DuckDB Parallelization**: 4 threads per connection
- **Alphabet Chunking**: 13 chunks (AB, CD, ..., YZ) reduce blocking search space
- **Typical Runtime**: 
  - 5K new records vs 100K existing: ~30-60 seconds
  - Scales linearly with record count up to ~1M records
- **Memory**: DuckDB auto-manages; typically uses <2GB for medium datasets

## Troubleshooting

### No matches found
- **Check**: Are thresholds too high?
- **Try**: Reduce `total_weight_min` or `total_weight_min`
- **Check**: Do names/DOBs have data quality issues?

### Too many false positives
- **Check**: Thresholds too low
- **Try**: Increase weight thresholds or fuzzy similarity thresholds
- **Check**: Address matching configured?

### Unique ID conflicts
- **Check**: Hash-based IDs colliding?
- **Try**: Use longer hash (change hash function or parameters)
- **Check**: Named field has duplicates?

### Database errors
- **Check**: DuckDB file corrupted?
- **Try**: Delete `.duckdb/` directory and rerun
- **Check**: Disk space available?

## Future Enhancements

- [ ] Supervised learning scoring (xgboost model)
- [ ] Multi-pass blocking with adaptive thresholds
- [ ] Graphical output (cluster visualization)
- [ ] Interactive threshold tuning
- [ ] Incremental mode (append new records without full recompute)

## License

[Specify your license]

## Contact

For questions or issues, contact [your email/team]
