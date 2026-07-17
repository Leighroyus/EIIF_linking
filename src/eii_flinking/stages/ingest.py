from __future__ import annotations

import duckdb

from ..config import DatasetConfig, UniqueIdConfig


def _id_expression(uid: UniqueIdConfig) -> str:
    """Return a SQL expression that produces the unique record ID."""
    if uid.strategy == "named_field":
        # id column already renamed in the connector; just cast to string
        return "CAST(id AS VARCHAR)"
    # hash strategy: build id from standard field values
    cols = uid.hash_columns or []
    if not cols:
        raise ValueError("hash strategy requires at least one hash_column (standard field name)")
    concat_parts = " || '|' || ".join(f"COALESCE(CAST({c} AS VARCHAR), '')" for c in cols)
    if uid.hash_algorithm == "sha256":
        return f"hex(sha256({concat_parts}))"
    return f"md5({concat_parts})"


_NAME_EXPR = "NULLIF(UPPER(TRIM(COALESCE(CAST({col} AS VARCHAR), ''))), '')"
_ADDR_EXPR = "NULLIF(UPPER(TRIM(COALESCE(CAST({col} AS VARCHAR), ''))), '')"

_DOB_EXPR = """
    CASE
        WHEN {col} IS NULL THEN NULL
        WHEN REGEXP_FULL_MATCH(
                REPLACE(COALESCE(CAST({col} AS VARCHAR), ''), '-', ''),
                '[0-9]{{8}}'
             )
        THEN REPLACE(CAST({col} AS VARCHAR), '-', '')
        ELSE NULL
    END
""".strip()

_GENDER_EXPR = """
    CASE
        WHEN UPPER(TRIM(COALESCE(CAST({col} AS VARCHAR), ''))) IN ('M', 'MALE', '1')   THEN 'M'
        WHEN UPPER(TRIM(COALESCE(CAST({col} AS VARCHAR), ''))) IN ('F', 'FEMALE', '2') THEN 'F'
        ELSE NULL
    END
""".strip()


def normalise_table(
    conn: duckdb.DuckDBPyConnection,
    raw_table: str,
    out_table: str,
    uid: UniqueIdConfig,
) -> None:
    """Normalise raw staged data into a clean lnk table with standard schema."""
    id_expr = _id_expression(uid)
    conn.execute(f"""
        CREATE OR REPLACE TABLE {out_table} AS
        SELECT
            {id_expr}                               AS id,
            {_NAME_EXPR.format(col='first_name')}   AS first_name,
            {_NAME_EXPR.format(col='middle_name')}  AS middle_name,
            {_NAME_EXPR.format(col='last_name')}    AS last_name,
            {_DOB_EXPR.format(col='date_of_birth')} AS date_of_birth,
            {_GENDER_EXPR.format(col='gender')}     AS gender,
            {_ADDR_EXPR.format(col='address_line1')} AS address_line1,
            {_ADDR_EXPR.format(col='address_suburb')} AS address_suburb,
            {_ADDR_EXPR.format(col='address_state')} AS address_state,
            NULLIF(TRIM(COALESCE(CAST(postcode AS VARCHAR), '')), '') AS postcode
        FROM {raw_table}
        WHERE {id_expr} IS NOT NULL
          AND {id_expr} != ''
    """)


STG_A = "lnk.stg_a"
STG_B = "lnk.stg_b"


def run(
    conn: duckdb.DuckDBPyConnection,
    dataset_a_config: DatasetConfig,
    dataset_b_config: DatasetConfig,
) -> None:
    """Normalise staged raw tables into lnk.dataset_a and lnk.dataset_b."""
    normalise_table(conn, STG_A, "lnk.dataset_a", dataset_a_config.unique_id)
    normalise_table(conn, STG_B, "lnk.dataset_b", dataset_b_config.unique_id)
