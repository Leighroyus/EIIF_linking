from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from ..config import DatasetConfig
from .base import BaseConnector


class DatabaseConnector(BaseConnector):
    def _read_raw(self, config: DatasetConfig) -> pd.DataFrame:
        assert config.source.connection_string, "DB connector requires source.connection_string"
        engine = create_engine(config.source.connection_string)
        with engine.connect() as conn:
            if config.source.query:
                df = pd.read_sql(text(config.source.query), conn, dtype=str)
            elif config.source.table_name:
                df = pd.read_sql(text(f"SELECT * FROM {config.source.table_name}"), conn, dtype=str)
            else:
                raise ValueError("DB connector requires either source.query or source.table_name")
        # Ensure all values are strings; nulls become None
        return df.astype(object).where(df.notna(), None).astype(str).replace("None", None)

    @staticmethod
    def columns(connection_string: str, table_name: str) -> list[str]:
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            df = pd.read_sql(text(f"SELECT * FROM {table_name} LIMIT 0"), conn)
        return list(df.columns)
