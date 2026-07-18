from __future__ import annotations

from ..config import DatasetConfig
from .base import BaseConnector
from .csv_connector import CsvConnector
from .database_connector import DatabaseConnector
from .excel_connector import ExcelConnector


def get_connector(source_type: str) -> BaseConnector:
    match source_type.lower():
        case "csv":
            return CsvConnector()
        case "excel" | "xlsx" | "xls":
            return ExcelConnector()
        case "database" | "db" | "sql":
            return DatabaseConnector()
        case _:
            raise ValueError(f"Unknown source_type: {source_type!r}. Expected csv, excel, or database.")


def load_dataset(config: DatasetConfig, table_name: str, conn) -> None:
    connector = get_connector(config.source.source_type)
    connector.load_to_duckdb(config, table_name, conn)
