from __future__ import annotations

from io import BytesIO

import pandas as pd

from ..config import DatasetConfig
from .base import BaseConnector


class CsvConnector(BaseConnector):
    def _read_raw(self, config: DatasetConfig) -> pd.DataFrame:
        assert config.source.file_path, "CSV connector requires source.file_path"
        return pd.read_csv(
            config.source.file_path,
            dtype=str,
            keep_default_na=False,
            encoding=config.source.encoding,
        )

    def _read_from_bytes(self, data: bytes, config: DatasetConfig) -> pd.DataFrame:
        return pd.read_csv(
            BytesIO(data),
            dtype=str,
            keep_default_na=False,
            encoding=config.source.encoding,
        )

    @staticmethod
    def preview_file(file_path: str, encoding: str = "utf-8", n: int = 5) -> pd.DataFrame:
        return pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding=encoding, nrows=n)

    @staticmethod
    def columns(file_path: str, encoding: str = "utf-8") -> list[str]:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding=encoding, nrows=0)
        return list(df.columns)
