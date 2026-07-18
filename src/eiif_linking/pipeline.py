from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd

from .config import AppConfig, DatasetConfig, load_config
from .connectors.factory import get_connector, load_dataset
from .duckdb.connection import connect
from .stages import blocking, ingest, post_linkage, proportions, scoring
from .stages.ingest import STG_A, STG_B


def _noop(_msg: str) -> None:
    pass


def run_pipeline(
    config: AppConfig,
    conn: duckdb.DuckDBPyConnection | None = None,
    progress: Callable[[str], None] = _noop,
) -> pd.DataFrame:
    """
    Execute the full linkage pipeline.

    Parameters
    ----------
    config:
        Parsed AppConfig (from load_config or built programmatically).
    conn:
        Optional existing DuckDB connection.  If None, a new connection is
        created using config.duckdb.database_path.
    progress:
        Callback invoked with a status string at each major step; useful for
        surfacing progress in the Streamlit UI.

    Returns
    -------
    pandas.DataFrame containing out.linkage_results.
    """
    if conn is None:
        conn = connect(config.duckdb.database_path)

    progress("Loading Dataset A…")
    _load(conn, config.dataset_a, STG_A)

    progress("Loading Dataset B…")
    _load(conn, config.dataset_b, STG_B)

    progress("Normalising records…")
    ingest.run(conn, config.dataset_a, config.dataset_b)

    progress("Calculating field frequencies…")
    proportions.run(conn)

    progress("Generating candidate pairs (blocking)…")
    blocking.run(conn, config.linkage.blocking)

    n_candidates = conn.execute("SELECT COUNT(*) FROM wrk.candidate_pairs").fetchone()[0]
    progress(f"Scoring {n_candidates:,} candidate pairs…")
    scoring.run(conn, config.linkage)

    progress("Applying thresholds and ranking matches…")
    post_linkage.run(conn, config.linkage)

    n_results = conn.execute("SELECT COUNT(*) FROM out.linkage_results").fetchone()[0]
    progress(f"Done — {n_results:,} matches found.")

    results_df = conn.execute("SELECT * FROM out.linkage_results ORDER BY a_id, match_rank").df()

    if config.output.format == "csv":
        _export_csv(results_df, config.output.file_path)
    elif config.output.format == "excel":
        _export_excel(results_df, config.output.file_path)

    return results_df


def run_pipeline_from_dataframes(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    config: AppConfig,
    conn: duckdb.DuckDBPyConnection | None = None,
    progress: Callable[[str], None] = _noop,
) -> pd.DataFrame:
    """
    Entry point for Streamlit (or any in-memory usage) where data is already
    loaded into pandas DataFrames rather than files.

    The DataFrames must already have standard column names (after field mapping
    is applied by the caller).
    """
    if conn is None:
        conn = connect(":memory:")

    progress("Registering Dataset A…")
    conn.register("_raw_a_df", df_a)
    conn.execute(f"CREATE OR REPLACE TABLE {STG_A} AS SELECT * FROM _raw_a_df")

    progress("Registering Dataset B…")
    conn.register("_raw_b_df", df_b)
    conn.execute(f"CREATE OR REPLACE TABLE {STG_B} AS SELECT * FROM _raw_b_df")

    progress("Normalising records…")
    ingest.run(conn, config.dataset_a, config.dataset_b)

    progress("Calculating field frequencies…")
    proportions.run(conn)

    progress("Generating candidate pairs (blocking)…")
    blocking.run(conn, config.linkage.blocking)

    n_candidates = conn.execute("SELECT COUNT(*) FROM wrk.candidate_pairs").fetchone()[0]
    progress(f"Scoring {n_candidates:,} candidate pairs…")
    scoring.run(conn, config.linkage)

    progress("Applying thresholds and ranking matches…")
    post_linkage.run(conn, config.linkage)

    n_results = conn.execute("SELECT COUNT(*) FROM out.linkage_results").fetchone()[0]
    progress(f"Done — {n_results:,} matches found.")

    return conn.execute("SELECT * FROM out.linkage_results ORDER BY a_id, match_rank").df()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load(
    conn: duckdb.DuckDBPyConnection,
    dataset_config: DatasetConfig,
    table_name: str,
) -> None:
    connector = get_connector(dataset_config.source.source_type)
    connector.load_to_duckdb(dataset_config, table_name, conn)


def _export_csv(df: pd.DataFrame, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _export_excel(df: pd.DataFrame, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="eiif-link",
        description="Cross-dataset record linkage between Set A and Set B.",
    )
    parser.add_argument("config", help="Path to linkage YAML config file")
    parser.add_argument("--no-export", action="store_true", help="Skip writing output file")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.no_export:
        config.output.format = "none"

    def log(msg: str) -> None:
        print(msg, flush=True)

    results = run_pipeline(config, progress=log)
    print(f"\nResults written to: {config.output.file_path}")
    print(results[["a_id", "b_id", "total_weight", "confidence", "match_rank"]].head(20).to_string())


if __name__ == "__main__":
    main()
