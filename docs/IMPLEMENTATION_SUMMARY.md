# EIIF Linking — Implementation Summary

## What This System Does

EIIF Linking is a cross-dataset record linkage system: given two independent person extracts (Set A and Set B), it finds A→B pairs that refer to the same person. It is **not** a deduplication system — it does not find duplicates within a single dataset.

It uses the Fellegi-Sunter probabilistic model with Jaro-Winkler string similarity, 4-rule alphabet-chunked blocking, and a config-driven field mapping layer that accepts CSV, Excel, or database inputs.

---

## Architecture

### Input Layer — Connectors

Each dataset is loaded independently through a connector that applies field mapping before handing data to the pipeline.

```
source file / database
    ↓
Connector (csv / excel / database)
    ↓
_apply_mapping(): source columns → standard pipeline fields
    ↓
lnk.stg_a / lnk.stg_b   (raw staging tables in DuckDB)
```

Key modules:
- `connectors/base.py` — `BaseConnector` abstract class; `load_to_duckdb()` and `_apply_mapping()` logic
- `connectors/csv_connector.py`, `excel_connector.py`, `database_connector.py` — concrete implementations
- `connectors/factory.py` — `get_connector(source_type)` and `load_dataset()` convenience wrapper

### Processing Layer — Pipeline Stages

Five sequential stages transform raw data to ranked match pairs:

```
lnk.stg_a / lnk.stg_b
    ↓ ingest.py
lnk.dataset_a / lnk.dataset_b   (normalised)
    ↓ proportions.py
lnk.prop_*                       (field frequency tables)
    ↓ blocking.py
wrk.candidate_pairs              (candidate A×B pairs)
    ↓ scoring.py
wrk.scored_pairs                 (with per-field and total weights)
    ↓ post_linkage.py
out.linkage_results              (filtered, ranked output)
```

### DuckDB Schema

Three schemas partition the work:
- **`lnk`** — stable data: normalised datasets, frequency tables
- **`wrk`** — transient: candidates, scores (can be dropped after pipeline runs)
- **`out`** — output: `out.linkage_results`

### Interface Layer

Three ways to run the pipeline:

| Interface | Entry point | Use case |
|-----------|-------------|----------|
| CLI | `eii-link config.yml` | Automation, scripts |
| Python API | `run_pipeline()` / `run_pipeline_from_dataframes()` | Integration, Jupyter |
| Streamlit GUI | `streamlit run src/eii_flinking/app/main.py` | Interactive exploration |

---

## Module Reference

### `schema.py`
- `STANDARD_FIELDS` — ordered list of all standard pipeline field names
- `REQUIRED_FIELDS` — frozenset `{id, first_name, last_name}`
- `DEFAULT_MATCH_PROBS` — default MP values per field
- `CONFIDENCE_HIGH_THRESHOLD = 30.0`, `CONFIDENCE_MEDIUM_THRESHOLD = 20.0`

### `config.py`
Config is parsed from YAML into typed dataclasses:
- `UniqueIdConfig` — strategy, field_name, hash_columns, hash_algorithm
- `SourceConfig` — file_path, sheet_name, connection_string, table_name, query
- `DatasetConfig` — source_type, source, unique_id, field_mapping, optional_fields
- `ThresholdConfig` — total_weight_min, confidence_high, confidence_medium, jw thresholds, max_matches_per_a_record
- `BlockingConfig` — alphabet_chunks, fuzzy_name_min
- `LinkageConfig` — thresholds, blocking, match_probabilities
- `OutputConfig` — format, file_path
- `DuckDBConfig` — database_path
- `AppConfig` — dataset_a, dataset_b, linkage, output, duckdb

`load_config(config_path)` returns `AppConfig`.

### `duckdb/connection.py`
- `connect(database_path=":memory:")` — opens DuckDB, runs `PRAGMA threads=4`, creates `lnk`, `wrk`, `out` schemas

### `connectors/base.py`
- `load_to_duckdb(config, table_name, conn)` — reads source, applies mapping, registers in DuckDB
- `_apply_mapping(df, config)` — reverses mapping dict (standard→source) to rename columns, pads missing standard fields as NULL, handles hash strategy (sets id=NULL for later hash computation in ingest)

### `stages/ingest.py`
- `STG_A = "lnk.stg_a"`, `STG_B = "lnk.stg_b"` — constants used by pipeline.py
- `_id_expression(uid)` — returns SQL expression for the ID column based on strategy
- `normalise_table(conn, raw_table, out_table, uid)` — normalises one dataset
- `run(conn, dataset_a_config, dataset_b_config)` — normalises both datasets

### `stages/proportions.py`
- `run(conn)` — creates `lnk.combined` view and `lnk.prop_{field}` frequency tables
- `MIN_PROP = 0.0001` floor prevents log₂(0)

### `stages/blocking.py`
- `run(conn, config)` — generates candidates via 4 rules, applies fuzzy gate, writes `wrk.candidate_pairs`
- Alphabet-chunked Rule 1 is the memory-efficient rule; Rules 2–4 are non-chunked

### `stages/scoring.py`
- `_jw_weight_expr(field, mp, jw_col, a_col, b_col, up_col)` — SQL CASE expression for JW-scored string fields
- `_exact_weight_expr(mp, a_col, b_col, up_col)` — exact-match-only SQL expression
- `_dob_weight_expr(mp)` — DOB-specific expression using `jw_dob` column alias
- `run(conn, config)` — joins candidate_pairs with datasets and prop tables, scores all fields, writes `wrk.scored_pairs`

### `stages/post_linkage.py`
- `run(conn, config)` — filters scored pairs by thresholds, adds `match_rank` and `is_best_match`, applies optional QUALIFY clause, writes `out.linkage_results`

### `pipeline.py`
- `run_pipeline(config, conn=None, progress=noop)` — file-based entry: loads datasets via connectors, calls all stages, exports if configured
- `run_pipeline_from_dataframes(df_a, df_b, config, conn=None, progress=noop)` — bypasses connectors; registers DataFrames directly as `lnk.stg_a` / `lnk.stg_b`, then calls same stages
- `main()` — CLI entry point; parses args, calls `run_pipeline`

### `app/main.py`
- Streamlit GUI with 4 tabs
- `_render_dataset_tab(prefix, label)` — tab renderer for dataset config
- Settings tab: sliders for all thresholds
- Run tab: builds `AppConfig` from `st.session_state`, calls `run_pipeline_from_dataframes`, shows metrics + filterable results table + download buttons

---

## Key Implementation Decisions

**Why DuckDB?**
In-memory columnar SQL engine with Python bindings. Handles the full pipeline as SQL transformations without intermediate file I/O. Supports fuzzy functions (`jaro_winkler_similarity`), QUALIFY clause, and efficient GROUP BY / ROW_NUMBER.

**Why log-odds (not probability scores)?**
Log-odds weights are additive across independent fields, making total_weight directly interpretable: each field's contribution is visible, and tuning one field doesn't require rescaling others.

**Why 4 blocking rules?**
Each rule targets a different data quality failure mode:
- Rule 1 (prefix match): general similarity
- Rule 2 (first name + DOB): surname change recovery  
- Rule 3 (last name + year-month): DOB typo recovery
- Rule 4 (first + last, no DOB): missing DOB recovery

**Why alphabet chunking?**
Chunking Rule 1 by last-name prefix limits the A×B cross-join size per batch. Rules 2–4 use more selective exact-match joins that don't require chunking.

**Why LEAST for UP?**
UP represents "how often would two random different people match on this field." Using the rarer of the two datasets' frequencies is conservative — it avoids over-weighting agreement on fields that are common in one dataset but rare in the other.

---

## Feature Checklist

### Input
- [x] CSV source
- [x] Excel source (xlsx, xls)
- [x] Database source (via SQLAlchemy connection string)
- [x] Named-field unique ID strategy
- [x] Hash-based unique ID (MD5 and SHA256)
- [x] Config-driven field mapping per dataset
- [x] Optional fields (NULL → 0 weight)

### Matching
- [x] Fellegi-Sunter log-odds probabilistic model
- [x] Jaro-Winkler string similarity for name and suburb fields
- [x] DOB-specific scoring with partial-match interpolation
- [x] Gender exact-match scoring
- [x] 4-rule blocking with fuzzy gate
- [x] Alphabet-chunked blocking (Rule 1)
- [x] Relaxed fuzzy threshold for DOB-anchored rules

### Output
- [x] All pairs above threshold (not just best match)
- [x] `match_rank` per A record
- [x] `is_best_match` flag
- [x] `confidence` band (HIGH/MEDIUM/LOW)
- [x] Field-level similarity scores (`sim_*`)
- [x] Field-level weight contributions (`wgt_*`)
- [x] Optional `max_matches_per_a_record` cap
- [x] CSV export
- [x] Excel export

### Interfaces
- [x] CLI (`eii-link`)
- [x] Python API (`run_pipeline`, `run_pipeline_from_dataframes`)
- [x] Streamlit GUI

---

**Last Updated:** 2026-07-17
