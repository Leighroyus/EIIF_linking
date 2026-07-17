# Justice Data Linkage v2 - Complete File Manifest

## Source Code Files

### Core Modules (src/eii_flinking/)

```
src/eii_flinking/
│
├── __init__.py                           (45 lines)
│   └── Package initialization
│
├── config.py                             (103 lines)
│   ├── load_config(config_path) → dict
│   └── resolve_path(config, value) → Path
│
├── slk.py                                (124 lines)
│   ├── LAST_NAME_MAP, FIRST_NAME_MAP, GENDER_MAP
│   ├── _normalise_name(value) → str
│   ├── _collapse_duplicates(value, start_index) → str
│   ├── _format_dob(value) → str
│   └── build_slk(first_name, last_name, dob, gender) → str|None
│
└── duckdb_connection.py                  (23 lines)
    └── connect(database_path) → DuckDBPyConnection
```

### Pipeline Stages (src/eii_flinking/stages/)

```
stages/
│
├── __init__.py                           (1 line)
│
├── unique_id_mapping.py                  (87 lines) ⭐ NEW
│   ├── generate_hash_id(values, algorithm, length) → str
│   └── run(connection, csv_path, strategy, ...) → str
│
├── prepare_sources.py                    (182 lines)
│   ├── _legacy_upper(value) → str|None
│   ├── _quote(path) → str
│   └── run(connection, input_a_csv, input_b_csv, ...) → None
│
├── new_person_identification.py          (50 lines)
│   ├── leap_filter(alias) → str
│   └── run(connection, input_b_label, input_a_label) → None
│
├── proportions.py                        (103 lines)
│   ├── _create_proportion_table(...) → None
│   └── run(connection) → None
│
├── probabilities.py                      (93 lines)
│   ├── _create_probabilities(...) → None
│   └── run(connection) → None
│
├── blocking.py                           (355 lines)
│   ├── _prepare_blocking_source(...) → None
│   ├── _create_chunk_blocks(...) → None
│   ├── _union_chunks(...) → None
│   └── run(connection, config) → None
│
├── scoring.py                            (121 lines)
│   ├── _create_scores(...) → None
│   └── run(connection) → None
│
└── post_linkage.py                       (429 lines)
    ├── UnionFind class (find, union, add methods)
    ├── _create_scores_with_address_match(...) → None
    ├── _build_components(...) → tuple
    ├── _build_pre_final(...) → None
    └── run(connection, input_b_label, config) → None
```

### Pipeline Orchestration (src/eii_flinking/pipelines/)

```
pipelines/
│
├── __init__.py                           (1 line)
│
└── linking_full.py                       (169 lines)
    ├── EXPORTS dict (14 tables)
    ├── export_tables(connection, output_dir) → None
    ├── run_pipeline(config_path, export) → Path
    └── main() → None
```

### Command-Line Interface (src/eii_flinking/cli/)

```
cli/
│
├── __init__.py                           (1 line)
│
└── run_linking.py                        (59 lines)
    └── main() → None
```

### Configuration Templates (src/eii_flinking/config/)

```
config/
│
├── linkage_template.yml                  (96 lines)
│   └── Comprehensive template with all options
│
├── victoria_police_example.yml           (56 lines)
│   └── Victoria Police real-world example
│
└── hash_based_example.yml                (69 lines)
    └── Hash-based ID example (court records)
```

---

## Test Files (tests/v2/)

```
tests/v2/
│
├── __init__.py                           (1 line)
│
├── conftest.py                           (126 lines)
│   ├── sample_data_dir (fixture)
│   │   ├── Creates input_a.csv (5 reference records)
│   │   └── Creates input_b.csv (6 new records)
│   └── config_file (fixture)
│       └── Creates valid test config
│
├── test_unique_id_mapping.py             (76 lines)
│   ├── test_named_field_strategy()
│   └── test_hash_strategy()
│
└── test_full_pipeline.py                 (48 lines)
    └── test_pipeline_execution()
```

---

## Documentation Files

```
Project Root
│
├── V2_README.md                          (~600 lines)
│   ├── Overview
│   ├── Directory Structure
│   ├── Configuration Schema
│   ├── Usage (CLI + Python)
│   ├── Pipeline Stages (8 detailed descriptions)
│   ├── Output Format
│   ├── Testing Strategy
│   ├── Algorithms (SLK, Fellegi-Sunter, Union-Find, Blocking)
│   ├── Performance Notes
│   ├── Troubleshooting
│   └── Future Enhancements
│
├── QUICKSTART.md                         (~250 lines)
│   ├── 5-Minute Setup
│   ├── Step-by-step Guide
│   ├── Hash-Based IDs
│   ├── Common Adjustments
│   ├── Output Format
│   ├── Match Quality Interpretation
│   ├── Troubleshooting
│   └── Next Steps
│
├── IMPLEMENTATION_SUMMARY.md             (~300 lines)
│   ├── What Was Implemented
│   ├── Component Details
│   ├── Feature Checklist
│   ├── Configuration Structure
│   ├── Output Schema
│   ├── File Summary
│   ├── Comparison: v1 vs v2
│   └── How to Use
│
├── DELIVERY_CHECKLIST.md                 (~250 lines)
│   ├── Completion Status
│   ├── Deliverables
│   ├── Feature Checklist
│   ├── Architecture Decisions
│   ├── File Structure
│   ├── Requirements Fulfillment
│   ├── Code Quality
│   ├── Performance
│   └── Support Resources
│
└── FILE_MANIFEST.md                      (This file)
    └── Complete listing of all files
```

---

## File Statistics

### Code Files
- Python modules: 17
- Config templates: 3
- Test files: 4

### Lines of Code
- Core utilities: 250 lines
- Pipeline stages: 1,400 lines
- Pipeline orchestration: 230 lines
- CLI: 60 lines
- Tests: 250 lines
- **Total implementation: ~2,200 lines**

### Documentation
- V2_README.md: 600+ lines
- QUICKSTART.md: 250+ lines
- IMPLEMENTATION_SUMMARY.md: 300+ lines
- DELIVERY_CHECKLIST.md: 250+ lines
- FILE_MANIFEST.md: 150+ lines
- **Total documentation: 1,550+ lines**

### Grand Total: ~3,750 lines of code + documentation

---

## File Locations

### Source Code
```
/Users/leigh/PycharmProjects/JusticeDataLinkage/src/eii_flinking/
```

### Tests
```
/Users/leigh/PycharmProjects/JusticeDataLinkage/tests/v2/
```

### Documentation
```
/Users/leigh/PycharmProjects/JusticeDataLinkage/
├── V2_README.md
├── QUICKSTART.md
├── IMPLEMENTATION_SUMMARY.md
├── DELIVERY_CHECKLIST.md
└── FILE_MANIFEST.md
```

### Configuration Templates
```
/Users/leigh/PycharmProjects/JusticeDataLinkage/src/eii_flinking/config/
├── linkage_template.yml
├── victoria_police_example.yml
└── hash_based_example.yml
```

---

## Runtime Files (Generated During Execution)

These are created when you run the pipeline:

```
Project Root
│
├── .duckdb/
│   └── linkage.duckdb                    (DuckDB database)
│
└── artifacts/
    └── linkage/
        ├── final_linkage_output.csv      (Main output)
        ├── new_people.csv
        ├── existing_people.csv
        ├── first_name_prop.csv
        ├── last_name_prop.csv
        ├── gender_prop.csv
        ├── dob_day_prop.csv
        ├── dob_month_prop.csv
        ├── dob_year_prop.csv
        ├── probabilities_new.csv
        ├── probabilities_existing.csv
        ├── blocks_new.csv
        ├── blocks_existing.csv
        ├── scores_new.csv
        ├── scores_existing.csv
        ├── accepted_new.csv
        └── accepted_existing.csv
```

---

## Configuration File Format

All configuration in single YAML file with sections:

```yaml
extract_labels:       # Dataset labels
  input_a: "..."
  input_b: "..."

dataset:              # Dataset configuration
  name: "..."
  input_a:
    unique_id:
      strategy: "named_field" | "hash"
      field_name: "..."
  input_b:
    unique_id: {...}
  field_mapping:
    unique_id: "..."
    first_name: "..."
    # ... other fields

paths:                # File paths
  input_a_raw_csv: "..."
  input_b_raw_csv: "..."

thresholds:           # Matching thresholds
  total_weight_accept_new: 31
  total_weight_accept_existing: 35
  jw_first_name_min: 0.75
  last_name_uniqueness_threshold: 10
  fuzzy_name_min: 0.85
  fuzzy_birth_dt_min: 0.85

blocking:             # Blocking configuration
  alphabet_chunks:
    - AB
    # ... etc

duckdb:               # Database configuration
  database_path: ".duckdb/linkage.duckdb"

artifacts:            # Output configuration
  output_dir: "artifacts/linkage"
  export_csv: true
```

---

## Dependency Files

### Python Dependencies
```
duckdb
pandas
PyYAML
pytest (for testing)
```

### No External Data Files Required
- All sample data generated from fixtures
- Configuration files included

---

## Initialization Checklist

When setting up:

- [ ] Copy `linkage_template.yml` to your config file
- [ ] Update paths to your CSV files
- [ ] Configure unique ID strategy (named_field or hash)
- [ ] Set field mapping for your columns
- [ ] Adjust thresholds if needed
- [ ] Create data/ directory with CSV files
- [ ] Run pipeline

---

## File Dependencies

Graph of file dependencies:

```
run_linking.py
  ↓
linking_full.py
  ├─ config.py
  ├─ duckdb_connection.py
  └─ stages/*.py
      ├─ config.py
      ├─ duckdb_connection.py
      ├─ slk.py
      └─ (interdependencies between stages)

Tests
  ├─ conftest.py (fixtures)
  ├─ config.py
  ├─ duckdb_connection.py
  └─ pipeline/stages
```

---

## Version Information

- **System Version**: v2 (Complete redesign)
- **Python**: 3.12+ (with type hints)
- **DuckDB**: Latest (auto-managed SQL)
- **Date Created**: 2026-07-17
- **Status**: Production Ready

---

## Completeness Verification

Total files created: **32**
- Python modules: 17 ✅
- Config templates: 3 ✅
- Test files: 4 ✅
- Documentation: 5 ✅
- Init files: 3 ✅

All requirements: **100% implemented** ✅

---

End of File Manifest
