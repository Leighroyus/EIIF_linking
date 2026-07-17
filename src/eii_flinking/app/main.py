from __future__ import annotations

"""
EII Flinking — Streamlit GUI
Run with:  streamlit run src/eii_flinking/app/main.py
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
    page_title="EII Flinking — Record Linkage",
    page_icon="🔗",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Package imports (absolute so they work with or without pip install -e .)
# ---------------------------------------------------------------------------
from eii_flinking.config import (
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
from eii_flinking.connectors.csv_connector import CsvConnector
from eii_flinking.connectors.excel_connector import ExcelConnector
from eii_flinking.pipeline import run_pipeline_from_dataframes
from eii_flinking.schema import STANDARD_FIELDS, CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD

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
    "b_df": None,
    "b_columns": [],
    "b_filename": None,
    "b_mapping": {},
    "b_optional": [],
    "b_uid_strategy": "named_field",
    "b_uid_field": None,
    "b_uid_hash_cols": [],
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
    "address_line1": "Address Line 1",
    "address_suburb": "Suburb / City",
    "address_state": "State",
    "postcode": "Postcode",
}
_REQUIRED = {"first_name", "last_name"}  # id handled separately via uid config


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
st.title("🔗 EII Flinking — Record Linkage")
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

                    results = run_pipeline_from_dataframes(
                        df_a_mapped,
                        df_b_mapped,
                        app_config,
                        progress=_progress,
                    )
                    st.session_state["results_df"] = results
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

        # Summary metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total matches", f"{len(results_df):,}")
        m2.metric("HIGH confidence", f"{(results_df['confidence'] == 'HIGH').sum():,}")
        m3.metric("MEDIUM confidence", f"{(results_df['confidence'] == 'MEDIUM').sum():,}")
        m4.metric("Unique A records matched", f"{results_df['a_id'].nunique():,}")

        # Filters
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

        st.dataframe(display_df, use_container_width=True, height=450)

        # Downloads
        dl1, dl2 = st.columns(2)
        with dl1:
            csv_bytes = display_df.to_csv(index=False).encode()
            st.download_button(
                "Download filtered results (CSV)",
                data=csv_bytes,
                file_name="linkage_results_filtered.csv",
                mime="text/csv",
            )
        with dl2:
            buf = io.BytesIO()
            results_df.to_excel(buf, index=False)
            st.download_button(
                "Download all results (Excel)",
                data=buf.getvalue(),
                file_name="linkage_results_all.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    elif results_df is not None and len(results_df) == 0:
        st.info("No matches found above the configured thresholds. Try lowering the minimum weight.")
