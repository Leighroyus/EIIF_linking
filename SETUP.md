# EIIF Linking - Setup Guide

Complete step-by-step guide to set up and run the EIIF Linking record linkage system.

## Prerequisites

- Python 3.12 or later
- pip or conda for package management
- Git (already installed if you cloned this repo)
- 2GB+ available disk space (for DuckDB)

## Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/Leighroyus/EIIF_linking.git
cd EIIF_linking
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Using venv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using conda
conda create -n eii-flinking python=3.12
conda activate eii-flinking
```

### Step 3: Install Dependencies

```bash
pip install duckdb pandas PyYAML pytest
```

Core Dependencies:
- duckdb (1.0+) - In-memory SQL database for data processing
- pandas (2.0+) - Data frame operations
- PyYAML (6.0+) - YAML configuration parsing
- pytest (7.0+) - Testing framework (optional, only if running tests)

### Step 4: Verify Installation

```bash
python -c "import duckdb, pandas, yaml; print('All dependencies installed')"
```

## Project Structure

```
EIIF_linking/
├── src/eii_flinking/              # Main package
│   ├── config.py                  # Configuration management
│   ├── slk.py                     # Soundex-like key generation
│   ├── duckdb_connection.py       # Database connection
│   ├── stages/                    # 8 pipeline stages
│   ├── pipelines/                 # Main pipeline
│   ├── cli/                       # CLI entry point
│   └── config/                    # Configuration templates
├── tests/v2/                      # Test suite
├── README.md                      # Main documentation
├── SETUP.md                       # This file
├── QUICKSTART.md                  # 5-minute quick start
└── V2_README.md                   # Comprehensive reference
```

## Configuration Setup

### Option 1: Quick Start (Recommended)

```bash
cp config/example_linkage.yml config/my_linkage.yml
# Edit with your settings
```

### Option 2: Named Field IDs

```bash
cp src/eii_flinking/config/victoria_police_example.yml config/my_linkage.yml
# Edit paths and field mappings
```

### Option 3: Hash-Based IDs

```bash
cp src/eii_flinking/config/hash_based_example.yml config/my_linkage.yml
# Update hash_columns to match your data
```

## Preparing Your Data

CSV files should have standard columns:
- first_name, middle_name, surname
- date_of_birth (YYYY-MM-DD or YYYYMMDD)
- gender (M/F/U)
- street_number, street_name, suburb, state (optional)
- Plus a unique_id column OR columns to hash

### Example CSV

```csv
person_id,first_name,middle_name,surname,date_of_birth,gender,street_number,street_name,suburb,state
P001,John,Michael,Smith,1980-01-15,M,123,Main Street,Springfield,IL
P002,Mary,Elizabeth,Johnson,1975-03-22,F,456,Oak Avenue,Shelbyville,IL
```

### Field Mapping in Configuration

```yaml
dataset:
  field_mapping:
    unique_id: "person_id"
    first_name: "first_name"
    surname: "surname"
    date_of_birth: "dob"
    gender: "sex_code"
```

## Running the Pipeline

### Command Line

```bash
# Basic run
python -m eii_flinking.pipeline --config config/my_linkage.yml

# With CSV export
python -m eii_flinking.pipeline --config config/my_linkage.yml --export
```

### Python API

```python
from eii_flinking.pipelines.linking_full import run_pipeline

db_path = run_pipeline("config/my_linkage.yml", export=True)
print(f"Results saved to: {db_path}")
```

## Accessing Results

### Query Results via Python

```python
import duckdb

conn = duckdb.connect(".duckdb/linkage.duckdb", read_only=True)

# Get all matched records
results = conn.execute("""
    SELECT CLUSTER_ID, PERSON_ID, FIRST_NAME, LAST_NAME, 
           BIRTH_DT, DATA_SOURCE, AVG_MATCH_WEIGHT
    FROM out.final_linkage_output
    ORDER BY CLUSTER_ID, PERSON_ID
""").fetch_df()

print(results)
conn.close()
```

### Query Results via CSV

```bash
cat artifacts/linkage/final_linkage_output.csv
```

## Running Tests

```bash
# All tests
pytest tests/v2/ -v

# Specific test
pytest tests/v2/test_unique_id_mapping.py -v

# With coverage
pytest tests/v2/ --cov=eii_flinking -v
```

## Troubleshooting

### DuckDB Connection Failed

```bash
rm -rf .duckdb/
python -m eii_flinking.pipeline --config config/my_linkage.yml
```

### CSV File Not Found

1. Check file paths in config are absolute or relative to project root
2. Verify CSV files exist
3. Check for typos in file paths

### Column Not Found

1. Verify CSV column names match field_mapping in config
2. Check for extra spaces in column names
3. Print CSV columns: head -1 data/input_a.csv

### Module Import Error

```bash
pip install --force-reinstall duckdb pandas PyYAML
```

### Import eii_flinking Not Found

```bash
cd /path/to/EIIF_linking
source venv/bin/activate
python -m eii_flinking.pipeline --config config/my_linkage.yml
```

## Performance Tuning

### For Large Datasets (100K+ records)

```yaml
thresholds:
  fuzzy_name_min: 0.90
  fuzzy_birth_dt_min: 0.90
```

### For Small Datasets (< 1K records)

```yaml
thresholds:
  total_weight_accept_new: 28
  fuzzy_name_min: 0.80
```

## Verification

Test your setup:

```bash
python -c "
import duckdb
import pandas
import yaml
from eii_flinking.config import load_config
from eii_flinking.slk import build_slk
print('Setup successful!')
"
```

## Next Steps

1. Review [QUICKSTART.md](QUICKSTART.md) for 5-minute quick start
2. Prepare your CSV files
3. Configure pipeline (copy config template, update paths)
4. Run pipeline
5. Validate results

## Documentation

- [README.md](README.md) - Overview
- [QUICKSTART.md](QUICKSTART.md) - 5-minute setup
- [V2_README.md](V2_README.md) - Comprehensive reference (600+ lines)
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Architecture

---

Last Updated: 2026-07-17
Status: Production Ready
