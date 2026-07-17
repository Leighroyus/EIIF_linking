from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    DEFAULT_MATCH_PROBS,
    JW_PARTIAL_MATCH,
)


@dataclass
class UniqueIdConfig:
    strategy: str = "named_field"          # "named_field" | "hash"
    field_name: str | None = None          # source column (named_field)
    hash_columns: list[str] = field(default_factory=list)  # standard fields (hash)
    hash_algorithm: str = "md5"            # md5 | sha256


@dataclass
class SourceConfig:
    source_type: str                        # csv | excel | database
    file_path: str | None = None
    sheet_name: str | None = None
    encoding: str = "utf-8"
    connection_string: str | None = None   # SQLAlchemy URL
    table_name: str | None = None
    query: str | None = None


@dataclass
class DatasetConfig:
    source: SourceConfig
    unique_id: UniqueIdConfig
    field_mapping: dict[str, str]          # standard_field -> source_column
    optional_fields: list[str] = field(default_factory=list)
    transforms: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThresholdConfig:
    total_weight_min: float = CONFIDENCE_MEDIUM_THRESHOLD
    confidence_high: float = CONFIDENCE_HIGH_THRESHOLD
    confidence_medium: float = CONFIDENCE_MEDIUM_THRESHOLD
    jw_first_name_min: float = JW_PARTIAL_MATCH
    jw_last_name_min: float = JW_PARTIAL_MATCH
    max_matches_per_a_record: int | None = None  # None = all above threshold


@dataclass
class BlockingConfig:
    alphabet_chunks: list[str] = field(default_factory=lambda: [
        "AB", "CD", "EF", "GH", "IJ", "KL", "MN", "OP", "QR", "ST", "UV", "WXYZ",
    ])
    fuzzy_name_min: float = 0.85
    fuzzy_dob_min: float = 0.85


@dataclass
class LinkageConfig:
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    blocking: BlockingConfig = field(default_factory=BlockingConfig)
    match_probabilities: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MATCH_PROBS)
    )


@dataclass
class OutputConfig:
    format: str = "csv"          # csv | excel
    file_path: str = "results/linkage_results.csv"
    include_field_similarities: bool = False


@dataclass
class DuckDBConfig:
    database_path: str = ":memory:"


@dataclass
class AppConfig:
    dataset_a: DatasetConfig
    dataset_b: DatasetConfig
    linkage: LinkageConfig
    output: OutputConfig
    duckdb: DuckDBConfig
    _config_path: Path | None = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _resolve(config_dir: Path, value: str) -> str:
    p = Path(value)
    return str(config_dir / p) if not p.is_absolute() else value


def _parse_unique_id(raw: dict) -> UniqueIdConfig:
    return UniqueIdConfig(
        strategy=raw.get("strategy", "named_field"),
        field_name=raw.get("field_name"),
        hash_columns=raw.get("hash_columns", []),
        hash_algorithm=raw.get("hash_algorithm", "md5"),
    )


def _parse_source(raw: dict, config_dir: Path) -> SourceConfig:
    src = raw.get("source", {})
    file_path = src.get("file_path")
    if file_path:
        file_path = _resolve(config_dir, file_path)
    return SourceConfig(
        source_type=raw["source_type"],
        file_path=file_path,
        sheet_name=src.get("sheet_name"),
        encoding=src.get("encoding", "utf-8"),
        connection_string=src.get("connection_string"),
        table_name=src.get("table_name"),
        query=src.get("query"),
    )


def _parse_dataset(raw: dict, config_dir: Path) -> DatasetConfig:
    return DatasetConfig(
        source=_parse_source(raw, config_dir),
        unique_id=_parse_unique_id(raw.get("unique_id", {})),
        field_mapping=raw["field_mapping"],
        optional_fields=raw.get("optional_fields", []),
        transforms=raw.get("transforms", {}),
    )


def load_config(config_path: str | Path) -> AppConfig:
    config_path = Path(config_path).resolve()
    config_dir = config_path.parent

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    linkage_raw = raw.get("linkage", {})
    thresholds_raw = linkage_raw.get("thresholds", {})
    thresholds = ThresholdConfig(
        total_weight_min=thresholds_raw.get("total_weight_min", CONFIDENCE_MEDIUM_THRESHOLD),
        confidence_high=thresholds_raw.get("confidence_high", CONFIDENCE_HIGH_THRESHOLD),
        confidence_medium=thresholds_raw.get("confidence_medium", CONFIDENCE_MEDIUM_THRESHOLD),
        jw_first_name_min=thresholds_raw.get("jw_first_name_min", JW_PARTIAL_MATCH),
        jw_last_name_min=thresholds_raw.get("jw_last_name_min", JW_PARTIAL_MATCH),
        max_matches_per_a_record=thresholds_raw.get("max_matches_per_a_record"),
    )
    blocking_raw = linkage_raw.get("blocking", {})
    blocking = BlockingConfig(
        alphabet_chunks=blocking_raw.get("alphabet_chunks", BlockingConfig().alphabet_chunks),
        fuzzy_name_min=blocking_raw.get("fuzzy_name_min", 0.85),
        fuzzy_dob_min=blocking_raw.get("fuzzy_dob_min", 0.85),
    )
    linkage = LinkageConfig(
        thresholds=thresholds,
        blocking=blocking,
        match_probabilities={**DEFAULT_MATCH_PROBS, **linkage_raw.get("match_probabilities", {})},
    )

    output_raw = raw.get("output", {})
    output_file = output_raw.get("file_path", "results/linkage_results.csv")
    output = OutputConfig(
        format=output_raw.get("format", "csv"),
        file_path=_resolve(config_dir, output_file),
        include_field_similarities=output_raw.get("include_field_similarities", False),
    )

    duckdb_raw = raw.get("duckdb", {})
    db_path = duckdb_raw.get("database_path", ":memory:")
    if db_path != ":memory:":
        db_path = _resolve(config_dir, db_path)

    return AppConfig(
        dataset_a=_parse_dataset(raw["dataset_a"], config_dir),
        dataset_b=_parse_dataset(raw["dataset_b"], config_dir),
        linkage=linkage,
        output=output,
        duckdb=DuckDBConfig(database_path=db_path),
        _config_path=config_path,
    )
