# EIIF Linking — File Manifest

## Source Code (`src/eii_flinking/`)

```
src/eii_flinking/
├── __init__.py
├── schema.py                     # STANDARD_FIELDS, REQUIRED_FIELDS, DEFAULT_MATCH_PROBS
├── config.py                     # AppConfig dataclasses + load_config()
├── pipeline.py                   # run_pipeline(), run_pipeline_from_dataframes(), main()
├── slk.py                        # build_slk() — Soundex-like key generation
│
├── duckdb/
│   ├── __init__.py
│   └── connection.py             # connect() — DuckDB with lnk/wrk/out schemas
│
├── connectors/
│   ├── __init__.py
│   ├── base.py                   # BaseConnector, load_to_duckdb(), _apply_mapping()
│   ├── csv_connector.py          # CsvConnector
│   ├── excel_connector.py        # ExcelConnector
│   ├── database_connector.py     # DatabaseConnector (SQLAlchemy)
│   └── factory.py                # get_connector(), load_dataset()
│
├── stages/
│   ├── __init__.py
│   ├── ingest.py                 # STG_A, STG_B, normalise_table(), run()
│   ├── proportions.py            # lnk.prop_* frequency tables, run()
│   ├── blocking.py               # 4-rule blocking + fuzzy gate, run()
│   ├── scoring.py                # log-odds weight expressions, run()
│   └── post_linkage.py           # filtering, ranking → out.linkage_results, run()
│
└── app/
    ├── __init__.py
    └── main.py                   # Streamlit GUI — 4-tab interface
```

**Total: 18 Python modules**

## Configuration

```
config/
└── example_linkage.yml           # Annotated template with all options
```

## Documentation

```
README.md                         # Project overview, features, quick start
SETUP.md                          # Installation, configuration, running, results

docs/
├── QUICKSTART.md                 # 5-minute setup guide
├── REFERENCE.md                  # Complete config + algorithm reference
├── IMPLEMENTATION_SUMMARY.md     # Architecture and module breakdown
├── DELIVERY_CHECKLIST.md         # Feature checklist and completion status
├── FILE_MANIFEST.md              # This file
└── INDEX.md                      # Documentation navigation guide
```

## Project Root Files

```
pyproject.toml                    # Package definition, dependencies, CLI entry point
.gitignore                        # Excludes: __pycache__, .venv, *.duckdb, results/, .idea/
```

---

## File Dependency Graph

```
eii-link (CLI)
    ↓
pipeline.py
    ├── config.py
    ├── duckdb/connection.py
    ├── connectors/factory.py
    │       └── connectors/base.py
    │               ├── csv_connector.py
    │               ├── excel_connector.py
    │               └── database_connector.py
    └── stages/
            ├── ingest.py     ← uses schema.py
            ├── proportions.py
            ├── blocking.py   ← uses config.py
            ├── scoring.py    ← uses config.py, schema.py
            └── post_linkage.py ← uses config.py

app/main.py
    └── pipeline.py (run_pipeline_from_dataframes)
```

---

## Runtime Files (Generated)

When the pipeline runs with a persistent database path:

```
.duckdb/
└── linkage.duckdb            # DuckDB database (if database_path set to a file)

results/
└── linkage_results.csv       # Output file (if output.file_path configured)
```

When run in `:memory:` mode (default), no files are written unless a `file_path` is set under `output`.

---

## Key Constants and API Surface

### `schema.py`
- `STANDARD_FIELDS: list[str]` — ordered pipeline field names
- `REQUIRED_FIELDS: frozenset` — `{id, first_name, last_name}`
- `DEFAULT_MATCH_PROBS: dict[str, float]` — per-field MP defaults
- `CONFIDENCE_HIGH_THRESHOLD = 30.0`
- `CONFIDENCE_MEDIUM_THRESHOLD = 20.0`

### `pipeline.py`
- `run_pipeline(config: str | Path, conn=None, progress=noop) → pd.DataFrame`
- `run_pipeline_from_dataframes(df_a, df_b, config: AppConfig, conn=None, progress=noop) → pd.DataFrame`

### `config.py`
- `load_config(config_path: str | Path) → AppConfig`

### `slk.py`
- `build_slk(first_name, last_name, dob, gender) → str | None`

### `duckdb/connection.py`
- `connect(database_path: str = ":memory:") → DuckDBPyConnection`

---

## Initialization Checklist

When setting up a new linkage job:

- [ ] Copy `config/example_linkage.yml` to `config/my_linkage.yml`
- [ ] Update `dataset_a.source.file_path` (or connection details)
- [ ] Update `dataset_b.source.file_path` (or connection details)
- [ ] Configure `unique_id` strategy for each dataset
- [ ] Set `field_mapping` for each dataset (map source columns to standard fields)
- [ ] List sparse/optional fields in `optional_fields`
- [ ] Adjust thresholds if needed (start with defaults)
- [ ] Set `output.file_path` if you want a CSV export
- [ ] Run: `eii-link config/my_linkage.yml`

---

**Last Updated:** 2026-07-17
