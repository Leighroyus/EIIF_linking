from __future__ import annotations

"""
EIIF Linking — Streamlit GUI
Run with:  streamlit run src/eiif_linking/app/main.py
"""

import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure the src/ directory is on sys.path so absolute imports work whether or
# not the package has been installed with `pip install -e .`.
_src = Path(__file__).resolve().parents[3]  # …/EIIFlinking/src
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EIIF Linking — Record Linkage",
    page_icon="🔗",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Package imports (absolute so they work with or without pip install -e .)
# ---------------------------------------------------------------------------
from eiif_linking.duckdb.connection import connect as _duckdb_connect
from eiif_linking.config import (
    AppConfig,
    BlockingConfig,
    DatasetConfig,
    DuckDBConfig,
    LinkageConfig,
    OutputConfig,
    SourceConfig,
    ThresholdConfig,
    UniqueIdConfig,
)
from eiif_linking.connectors.csv_connector import CsvConnector
from eiif_linking.connectors.excel_connector import ExcelConnector
from eiif_linking.pipeline import run_pipeline_from_dataframes
from eiif_linking.schema import STANDARD_FIELDS, CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD

# ---------------------------------------------------------------------------
# Session-state defaults
# ---------------------------------------------------------------------------
_DEFAULTS: dict[str, Any] = {
    "a_df": None,
    "a_columns": [],
    "a_filename": None,
    "a_mapping": {},
    "a_optional": [],
    "a_uid_strategy": "named_field",
    "a_uid_field": None,
    "a_uid_hash_cols": [],
    "a_df_mapped": None,
    "a_df_normalised": None,
    "b_df": None,
    "b_columns": [],
    "b_filename": None,
    "b_mapping": {},
    "b_optional": [],
    "b_uid_strategy": "named_field",
    "b_uid_field": None,
    "b_uid_hash_cols": [],
    "b_df_mapped": None,
    "b_df_normalised": None,
    "total_weight_min": CONFIDENCE_MEDIUM_THRESHOLD,
    "confidence_high": CONFIDENCE_HIGH_THRESHOLD,
    "confidence_medium": CONFIDENCE_MEDIUM_THRESHOLD,
    "jw_fn_min": 0.75,
    "jw_ln_min": 0.75,
    "max_matches": 0,  # 0 = all above threshold
    "fuzzy_name_min": 0.85,
    "results_df": None,
    "run_log": [],
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
_NOT_AVAILABLE = "— not available —"
_DISPLAY_NAMES = {
    "id": "Record ID",
    "first_name": "First Name",
    "middle_name": "Middle Name",
    "last_name": "Last Name",
    "date_of_birth": "Date of Birth",
    "gender": "Gender",
    "address_full": "Full Address (auto-parsed)",
    "address_street_number": "Street Number",
    "address_street_name": "Street Name",
    "address_town_or_suburb": "Town / Suburb",
    "address_lga": "LGA (Local Government Area)",
}
_REQUIRED = {"first_name", "last_name"}  # id handled separately via uid config

# Columns stripped from exports when the user ticks "Omit PII columns".
# Covers all view modes (matched pairs view and All Set A/B views use different prefixed names).
_PII_COLS = frozenset({
    # Person fields — both sides
    "a_first_name", "a_middle_name", "a_last_name", "a_dob", "a_gender",
    "b_first_name", "b_middle_name", "b_last_name", "b_dob", "b_gender",
    # Address fields — All Set A/B views
    "a_address_full", "a_street_number", "a_street_name", "a_town_or_suburb", "a_lga",
    "b_address_full", "b_street_number", "b_street_name", "b_town_or_suburb", "b_lga",
})


def _render_dataset_tab(prefix: str, label: str) -> None:
    """Render the full configuration tab for one dataset (A or B)."""
    st.subheader(f"Dataset {label} — Source File")

    uploaded = st.file_uploader(
        f"Upload Dataset {label} (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        key=f"{prefix}_uploader",
    )

    if uploaded is not None:
        # Only re-read if a new file was selected
        if uploaded.name != st.session_state.get(f"{prefix}_filename"):
            ext = Path(uploaded.name).suffix.lower()
            try:
                if ext == ".csv":
                    df = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
                else:
                    df = pd.read_excel(uploaded, dtype=str, keep_default_na=False)
                st.session_state[f"{prefix}_df"] = df
                st.session_state[f"{prefix}_columns"] = list(df.columns)
                st.session_state[f"{prefix}_filename"] = uploaded.name
                st.session_state[f"{prefix}_mapping"] = {}
            except Exception as exc:
                st.error(f"Could not read file: {exc}")

        df_loaded = st.session_state[f"{prefix}_df"]
        if df_loaded is not None:
            st.success(
                f"Loaded **{st.session_state[f'{prefix}_filename']}**: "
                f"{len(df_loaded):,} rows × {len(df_loaded.columns)} columns"
            )

    df = st.session_state[f"{prefix}_df"]
    cols = st.session_state[f"{prefix}_columns"]

    if df is None:
        st.info("Load a file above to configure field mapping.")
        return

    with st.expander("Preview (first 5 rows)", expanded=False):
        st.dataframe(df.head(5), use_container_width=True)

    st.divider()
    st.subheader("Unique Record ID")

    uid_strategy = st.radio(
        "ID strategy",
        ["Named field (use existing column)", "Hash (generate from field values)"],
        key=f"{prefix}_uid_radio",
        horizontal=True,
    )
    use_named = uid_strategy.startswith("Named")
    st.session_state[f"{prefix}_uid_strategy"] = "named_field" if use_named else "hash"

    if use_named:
        uid_field = st.selectbox(
            "Source column to use as ID",
            options=[_NOT_AVAILABLE] + cols,
            key=f"{prefix}_uid_field_sel",
        )
        st.session_state[f"{prefix}_uid_field"] = None if uid_field == _NOT_AVAILABLE else uid_field
    else:
        std_fields_no_id = [f for f in STANDARD_FIELDS if f != "id"]
        uid_hash_cols = st.multiselect(
            "Standard fields to hash together",
            options=std_fields_no_id,
            default=[f for f in ["first_name", "last_name", "date_of_birth"] if f in std_fields_no_id],
            format_func=lambda f: _DISPLAY_NAMES.get(f, f),
            key=f"{prefix}_uid_hash_sel",
            help="Select standard pipeline fields (after mapping) to concatenate and hash as the record ID.",
        )
        st.session_state[f"{prefix}_uid_hash_cols"] = uid_hash_cols

    st.divider()
    st.subheader("Field Mapping")
    st.caption(
        "Map each standard pipeline field to the matching column in your data. "
        "Fields marked **required** must be mapped."
    )

    # When address_full is set (or changes to a new value), auto-clear the four
    # address component fields so they default to unmapped.  The user can still
    # individually override any component field afterwards.
    _ADDR_COMPONENTS = [
        "address_street_number", "address_street_name",
        "address_town_or_suburb", "address_lga",
    ]
    _cur_full = st.session_state.get(f"{prefix}_map_address_full", _NOT_AVAILABLE)
    _prev_full = st.session_state.get(f"{prefix}_addr_full_prev", _NOT_AVAILABLE)
    if _cur_full != _NOT_AVAILABLE and _cur_full != _prev_full:
        for _comp in _ADDR_COMPONENTS:
            st.session_state[f"{prefix}_map_{_comp}"] = _NOT_AVAILABLE
    st.session_state[f"{prefix}_addr_full_prev"] = _cur_full

    mapping: dict[str, str] = {}
    optional_fields: list[str] = []

    # Skip 'id' — handled by unique_id config above
    for std_field in [f for f in STANDARD_FIELDS if f != "id"]:
        is_required = std_field in _REQUIRED
        label_text = _DISPLAY_NAMES.get(std_field, std_field)
        badge = " *(required)*" if is_required else ""

        c1, c2 = st.columns([2, 3])
        with c1:
            st.markdown(f"**{label_text}**{badge}")
        with c2:
            default_idx = 0
            # Try to pre-select a column with a similar name
            lower_cols = [c.lower() for c in cols]
            for hint in [std_field, std_field.replace("_", ""), std_field.split("_")[0]]:
                for i, lc in enumerate(lower_cols):
                    if hint in lc:
                        default_idx = i + 1  # +1 because index 0 = _NOT_AVAILABLE
                        break
                if default_idx:
                    break

            selected = st.selectbox(
                "",
                options=[_NOT_AVAILABLE] + cols,
                index=default_idx,
                key=f"{prefix}_map_{std_field}",
                label_visibility="collapsed",
            )

        # After the address_full row: hint that components will be auto-parsed,
        # and that the user can still map them individually to override.
        if std_field == "address_full" and selected != _NOT_AVAILABLE:
            st.caption(
                "↳ Street number, name, suburb, and LGA will be auto-parsed from this field. "
                "Map any component field below to override the parsed value."
            )

        if selected != _NOT_AVAILABLE:
            mapping[std_field] = selected
        elif not is_required:
            optional_fields.append(std_field)

    # All unmapped fields are optional by definition
    for std_field in [f for f in STANDARD_FIELDS if f != "id"]:
        if std_field not in mapping and std_field not in optional_fields:
            optional_fields.append(std_field)

    st.session_state[f"{prefix}_mapping"] = mapping
    st.session_state[f"{prefix}_optional"] = optional_fields


def _build_dataset_config(prefix: str, source_type_lower: str, file_path: str) -> DatasetConfig | None:
    mapping = st.session_state[f"{prefix}_mapping"]
    optional = st.session_state[f"{prefix}_optional"]
    uid_strategy = st.session_state[f"{prefix}_uid_strategy"]
    uid_field = st.session_state.get(f"{prefix}_uid_field")
    uid_hash_cols = st.session_state.get(f"{prefix}_uid_hash_cols", [])

    if not mapping.get("first_name") or not mapping.get("last_name"):
        return None  # caller shows error

    return DatasetConfig(
        source=SourceConfig(
            source_type=source_type_lower,
            file_path=file_path,
        ),
        unique_id=UniqueIdConfig(
            strategy=uid_strategy,
            field_name=uid_field,
            hash_columns=uid_hash_cols,
        ),
        field_mapping=mapping,
        optional_fields=optional,
    )


def _apply_mapping_to_df(df: pd.DataFrame, config: DatasetConfig) -> pd.DataFrame:
    """Return a DataFrame with standard column names (mirrors connector logic)."""
    reverse = {v: k for k, v in config.field_mapping.items()}
    if config.unique_id.strategy == "named_field" and config.unique_id.field_name:
        reverse[config.unique_id.field_name] = "id"
    renamed = df.rename(columns=reverse)
    for f in STANDARD_FIELDS:
        if f not in renamed.columns:
            renamed[f] = None
    if config.unique_id.strategy == "hash":
        renamed["id"] = None
    return renamed[STANDARD_FIELDS]


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
st.title("🔗 EIIF Linking — Record Linkage")
st.caption(
    "Link people across two independent datasets using probabilistic name, "
    "date-of-birth, and address matching."
)

tab_a, tab_b, tab_settings, tab_run = st.tabs(
    ["Dataset A", "Dataset B", "Linkage Settings", "Run & Results"]
)

with tab_a:
    _render_dataset_tab("a", "A")

with tab_b:
    _render_dataset_tab("b", "B")

with tab_settings:
    st.subheader("Match Thresholds")

    c1, c2 = st.columns(2)
    with c1:
        st.session_state["total_weight_min"] = st.slider(
            "Minimum total weight to accept a match",
            min_value=0.0, max_value=60.0,
            value=float(st.session_state["total_weight_min"]),
            step=1.0,
            help="Higher = stricter. Typical range: 15 (loose) to 35 (strict).",
        )
        st.session_state["confidence_high"] = st.slider(
            "HIGH confidence threshold",
            min_value=0.0, max_value=60.0,
            value=float(st.session_state["confidence_high"]),
            step=1.0,
        )
        st.session_state["confidence_medium"] = st.slider(
            "MEDIUM confidence threshold",
            min_value=0.0, max_value=60.0,
            value=float(st.session_state["confidence_medium"]),
            step=1.0,
        )
    with c2:
        st.session_state["jw_fn_min"] = st.slider(
            "Min first-name similarity (Jaro-Winkler)",
            min_value=0.0, max_value=1.0,
            value=float(st.session_state["jw_fn_min"]),
            step=0.05,
        )
        st.session_state["jw_ln_min"] = st.slider(
            "Min last-name similarity (Jaro-Winkler)",
            min_value=0.0, max_value=1.0,
            value=float(st.session_state["jw_ln_min"]),
            step=0.05,
        )
        max_matches_input = st.number_input(
            "Max B matches per A record (0 = all above threshold)",
            min_value=0, max_value=100,
            value=int(st.session_state["max_matches"]),
            step=1,
        )
        st.session_state["max_matches"] = max_matches_input

    st.divider()
    st.subheader("Blocking")
    st.session_state["fuzzy_name_min"] = st.slider(
        "Fuzzy blocking gate (min name similarity in candidate generation)",
        min_value=0.5, max_value=1.0,
        value=float(st.session_state["fuzzy_name_min"]),
        step=0.05,
        help="Lower = more candidates (slower but catches more edge cases).",
    )

with tab_run:
    st.subheader("Run Linkage")

    ready = (
        st.session_state["a_df"] is not None
        and st.session_state["b_df"] is not None
        and st.session_state["a_mapping"].get("first_name")
        and st.session_state["a_mapping"].get("last_name")
        and st.session_state["b_mapping"].get("first_name")
        and st.session_state["b_mapping"].get("last_name")
    )

    if not ready:
        st.warning(
            "Configure both Dataset A and Dataset B (including first_name and last_name "
            "mappings) before running."
        )
    else:
        run_clicked = st.button("Run Linkage", type="primary", use_container_width=True)
        if run_clicked:
            _run_log: list[str] = []
            status_placeholder = st.empty()

            def _progress(msg: str) -> None:
                _run_log.append(msg)
                status_placeholder.info(msg)

            try:
                a_source_type = st.session_state.get("a_source_type", "csv").lower()
                b_source_type = st.session_state.get("b_source_type", "csv").lower()

                config_a = _build_dataset_config("a", a_source_type, "")
                config_b = _build_dataset_config("b", b_source_type, "")

                if not config_a or not config_b:
                    st.error("Incomplete field mapping — first_name and last_name are required for both datasets.")
                else:
                    df_a_mapped = _apply_mapping_to_df(st.session_state["a_df"], config_a)
                    df_b_mapped = _apply_mapping_to_df(st.session_state["b_df"], config_b)

                    max_m = st.session_state["max_matches"]
                    app_config = AppConfig(
                        dataset_a=config_a,
                        dataset_b=config_b,
                        linkage=LinkageConfig(
                            thresholds=ThresholdConfig(
                                total_weight_min=st.session_state["total_weight_min"],
                                confidence_high=st.session_state["confidence_high"],
                                confidence_medium=st.session_state["confidence_medium"],
                                jw_first_name_min=st.session_state["jw_fn_min"],
                                jw_last_name_min=st.session_state["jw_ln_min"],
                                max_matches_per_a_record=max_m if max_m > 0 else None,
                            ),
                            blocking=BlockingConfig(
                                fuzzy_name_min=st.session_state["fuzzy_name_min"],
                            ),
                        ),
                        output=OutputConfig(format="none"),
                        duckdb=DuckDBConfig(database_path=":memory:"),
                    )

                    # Use a persistent connection so we can read lnk.dataset_a/b
                    # after the run — those tables have the real computed IDs
                    # (including hashes) that match results_df["a_id"/"b_id"].
                    conn = _duckdb_connect(":memory:")
                    results = run_pipeline_from_dataframes(
                        df_a_mapped,
                        df_b_mapped,
                        app_config,
                        conn=conn,
                        progress=_progress,
                    )
                    a_normalised = conn.execute("SELECT * FROM lnk.dataset_a").fetch_df()
                    b_normalised = conn.execute("SELECT * FROM lnk.dataset_b").fetch_df()
                    conn.close()

                    st.session_state["results_df"] = results
                    st.session_state["a_df_mapped"] = df_a_mapped
                    st.session_state["b_df_mapped"] = df_b_mapped
                    st.session_state["a_df_normalised"] = a_normalised
                    st.session_state["b_df_normalised"] = b_normalised
                    st.session_state["run_log"] = _run_log
                    status_placeholder.success(f"Complete — {len(results):,} matches found.")

            except Exception as exc:
                st.error(f"Pipeline error: {exc}")
                raise

    # ── Results ────────────────────────────────────────────────────────────────
    results_df: pd.DataFrame | None = st.session_state["results_df"]
    if results_df is not None and len(results_df) > 0:
        st.divider()
        st.subheader("Results")

        a_df_mapped: pd.DataFrame | None = st.session_state.get("a_df_mapped")
        b_df_mapped: pd.DataFrame | None = st.session_state.get("b_df_mapped")
        a_normalised: pd.DataFrame | None = st.session_state.get("a_df_normalised")
        b_normalised: pd.DataFrame | None = st.session_state.get("b_df_normalised")

        # Summary metrics
        n_a_total = len(a_normalised) if a_normalised is not None else "—"
        n_b_total = len(b_normalised) if b_normalised is not None else "—"
        n_a_matched = results_df["a_id"].nunique()
        n_b_matched = results_df["b_id"].nunique()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total match pairs", f"{len(results_df):,}")
        m2.metric("HIGH confidence", f"{(results_df['confidence'] == 'HIGH').sum():,}")
        m3.metric(
            "Set A matched",
            f"{n_a_matched:,} / {n_a_total:,}" if isinstance(n_a_total, int) else f"{n_a_matched:,}",
        )
        m4.metric(
            "Set B matched",
            f"{n_b_matched:,} / {n_b_total:,}" if isinstance(n_b_total, int) else f"{n_b_matched:,}",
        )

        # View selector
        st.divider()
        view_mode = st.radio(
            "View",
            ["Matched pairs", "All Set A records", "All Set B records"],
            horizontal=True,
            key="view_mode",
            help=(
                "Matched pairs: only records that linked. "
                "All Set A / All Set B: every record in that dataset, "
                "showing the best match where found and highlighting unmatched rows."
            ),
        )

        if view_mode == "Matched pairs":
            # ── Filters ───────────────────────────────────────────────────────
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                conf_filter = st.multiselect(
                    "Confidence",
                    options=["HIGH", "MEDIUM", "LOW"],
                    default=["HIGH", "MEDIUM", "LOW"],
                    key="conf_filter",
                )
            with fc2:
                best_only = st.checkbox("Best match only", value=False, key="best_only_filter")
            with fc3:
                min_weight_display = st.number_input(
                    "Min weight to display",
                    min_value=0.0,
                    value=float(st.session_state["total_weight_min"]),
                    step=1.0,
                    key="min_weight_display",
                )

            display_df = results_df[results_df["confidence"].isin(conf_filter)]
            display_df = display_df[display_df["total_weight"] >= min_weight_display]
            if best_only:
                display_df = display_df[display_df["is_best_match"]]
            download_name = "linkage_matched_pairs"

        elif view_mode == "All Set A records":
            if a_normalised is None:
                st.warning("Set A data not available — rerun the pipeline.")
                display_df = pd.DataFrame()
            else:
                # Best B match per A record (is_best_match), all available B columns
                _a_match_cols = [c for c in [
                    "a_id", "b_id", "total_weight", "confidence", "match_rank",
                    "b_first_name", "b_middle_name", "b_last_name",
                    "b_dob", "b_gender", "b_town_or_suburb", "b_street_name",
                ] if c in results_df.columns]
                best = results_df[results_df["is_best_match"]][_a_match_cols].copy()

                # lnk.dataset_a has all standard fields with real computed IDs
                a_view = (
                    a_normalised[list(STANDARD_FIELDS)]
                    .rename(columns={
                        "id": "a_id",
                        "first_name": "a_first_name",
                        "middle_name": "a_middle_name",
                        "last_name": "a_last_name",
                        "date_of_birth": "a_dob",
                        "gender": "a_gender",
                        "address_full": "a_address_full",
                        "address_street_number": "a_street_number",
                        "address_street_name": "a_street_name",
                        "address_town_or_suburb": "a_town_or_suburb",
                        "address_lga": "a_lga",
                    })
                )
                display_df = a_view.merge(best, on="a_id", how="left")
                display_df.insert(1, "matched", display_df["b_id"].notna())
                display_df = display_df.sort_values(["matched", "total_weight"], ascending=[False, False])
                if st.checkbox("Unmatched only", key="unmatched_only_a"):
                    display_df = display_df[~display_df["matched"]]
                    download_name = "linkage_unmatched_set_a"
                else:
                    download_name = "linkage_all_set_a"

        else:  # All Set B records
            if b_normalised is None:
                st.warning("Set B data not available — rerun the pipeline.")
                display_df = pd.DataFrame()
            else:
                # Best A match per B record (highest weight, one row per b_id)
                _b_match_cols = [c for c in [
                    "b_id", "a_id", "total_weight", "confidence",
                    "a_first_name", "a_middle_name", "a_last_name",
                    "a_dob", "a_gender", "a_town_or_suburb", "a_street_name",
                ] if c in results_df.columns]
                best = (
                    results_df
                    .sort_values("total_weight", ascending=False)
                    .drop_duplicates(subset=["b_id"])
                    [_b_match_cols]
                    .copy()
                )

                # lnk.dataset_b has all standard fields with real computed IDs
                b_view = (
                    b_normalised[list(STANDARD_FIELDS)]
                    .rename(columns={
                        "id": "b_id",
                        "first_name": "b_first_name",
                        "middle_name": "b_middle_name",
                        "last_name": "b_last_name",
                        "date_of_birth": "b_dob",
                        "gender": "b_gender",
                        "address_full": "b_address_full",
                        "address_street_number": "b_street_number",
                        "address_street_name": "b_street_name",
                        "address_town_or_suburb": "b_town_or_suburb",
                        "address_lga": "b_lga",
                    })
                )
                display_df = b_view.merge(best, on="b_id", how="left")
                display_df.insert(1, "matched", display_df["a_id"].notna())
                display_df = display_df.sort_values(["matched", "total_weight"], ascending=[False, False])
                if st.checkbox("Unmatched only", key="unmatched_only_b"):
                    display_df = display_df[~display_df["matched"]]
                    download_name = "linkage_unmatched_set_b"
                else:
                    download_name = "linkage_all_set_b"

        if len(display_df) > 0:
            st.dataframe(display_df, use_container_width=True, height=450)

            omit_pii = st.checkbox(
                "Omit PII columns from export (names, date of birth, gender, address)",
                value=False,
                key="omit_pii",
                help=(
                    "Removes personal identifiable information from the downloaded file. "
                    "Keeps record IDs, match weights, confidence, and similarity scores."
                ),
            )
            export_df = (
                display_df.drop(columns=[c for c in _PII_COLS if c in display_df.columns])
                if omit_pii else display_df
            )
            export_name = f"{download_name}_no_pii" if omit_pii else download_name

            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "Download (CSV)",
                    data=export_df.to_csv(index=False).encode(),
                    file_name=f"{export_name}.csv",
                    mime="text/csv",
                )
            with dl2:
                buf = io.BytesIO()
                export_df.to_excel(buf, index=False)
                st.download_button(
                    "Download (Excel)",
                    data=buf.getvalue(),
                    file_name=f"{export_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    elif results_df is not None and len(results_df) == 0:
        st.info("No matches found above the configured thresholds. Try lowering the minimum weight.")
