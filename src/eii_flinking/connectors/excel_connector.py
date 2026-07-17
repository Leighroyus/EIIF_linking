from __future__ import annotations

from io import BytesIO

import pandas as pd

from ..config import DatasetConfig
from .base import BaseConnector


class ExcelConnector(BaseConnector):
    def _read_raw(self, config: DatasetConfig) -> pd.DataFrame:
        assert config.source.file_path, "Excel connector requires source.file_path"
        return pd.read_excel(
            config.source.file_path,
            sheet_name=config.source.sheet_name or 0,
            dtype=str,
            keep_default_na=False,
        )

    def _read_from_bytes(self, data: bytes, config: DatasetConfig) -> pd.DataFrame:
        return pd.read_excel(
            BytesIO(data),
            sheet_name=config.source.sheet_name or 0,
            dtype=str,
            keep_default_na=False,
        )

    @staticmethod
    def sheet_names(file_path: str) -> list[str]:
        xl = pd.ExcelFile(file_path)
        return xl.sheet_names

    @staticmethod
    def columns(file_path: str, sheet_name: str | int = 0) -> list[str]:
        df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str, keep_default_na=False, nrows=0)
        return list(df.columns)
