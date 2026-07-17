from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO

import duckdb
import pandas as pd

from ..config import DatasetConfig
from ..schema import STANDARD_FIELDS


class BaseConnector(ABC):
    """Loads source data and registers it in DuckDB with standard column names."""

    def load_to_duckdb(
        self,
        config: DatasetConfig,
        table_name: str,
        conn: duckdb.DuckDBPyConnection,
    ) -> None:
        df = self._read_raw(config)
        df = self._apply_mapping(df, config)
        # Use a simple, safe temp view name derived from the target table
        tmp = "_tmp_load_" + table_name.replace(".", "_").replace("-", "_")
        conn.register(tmp, df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {tmp}")

    def load_from_bytes(
        self,
        data: bytes,
        config: DatasetConfig,
        table_name: str,
        conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Convenience entry point for Streamlit file-uploader bytes."""
        df = self._read_from_bytes(data, config)
        df = self._apply_mapping(df, config)
        tmp = "_tmp_load_" + table_name.replace(".", "_").replace("-", "_")
        conn.register(tmp, df)
        conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM {tmp}")

    @abstractmethod
    def _read_raw(self, config: DatasetConfig) -> pd.DataFrame:
        """Return a DataFrame with original source column names."""

    def _read_from_bytes(self, data: bytes, config: DatasetConfig) -> pd.DataFrame:
        raise NotImplementedError(f"{type(self).__name__} does not support bytes loading")

    def _apply_mapping(self, df: pd.DataFrame, config: DatasetConfig) -> pd.DataFrame:
        # Build reverse mapping: source_col -> standard_col
        reverse = {v: k for k, v in config.field_mapping.items()}

        # Handle unique_id for named_field strategy
        if config.unique_id.strategy == "named_field" and config.unique_id.field_name:
            reverse[config.unique_id.field_name] = "id"

        df = df.rename(columns=reverse)

        # Add any missing standard fields as None
        for f in STANDARD_FIELDS:
            if f not in df.columns:
                df[f] = None

        # For hash strategy, placeholder id = None (ingest will compute it)
        if config.unique_id.strategy == "hash":
            df["id"] = None

        return df[STANDARD_FIELDS]

    @staticmethod
    def preview(config: DatasetConfig, n: int = 5) -> pd.DataFrame:
        """Return first n rows of raw data without applying field mapping."""
        raise NotImplementedError
