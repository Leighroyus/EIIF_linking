from __future__ import annotations

import duckdb

from ..config import DatasetConfig, UniqueIdConfig


def _id_expression(uid: UniqueIdConfig) -> str:
    """Return a SQL expression that produces the unique record ID."""
    if uid.strategy == "named_field":
        return "CAST(id AS VARCHAR)"
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
    # Pull staged data, enrich address fields, write back before SQL normalisation.
    from ..address_parser import enrich_address_df
    df = conn.execute(f"SELECT * FROM {raw_table}").df()
    df = enrich_address_df(df)
    conn.register("_staged_enriched", df)
    conn.execute(f"CREATE OR REPLACE TABLE {raw_table} AS SELECT * FROM _staged_enriched")

    id_expr = _id_expression(uid)
    conn.execute(f"""
        CREATE OR REPLACE TABLE {out_table} AS
        SELECT
            {id_expr}                                           AS id,
            {_NAME_EXPR.format(col='first_name')}               AS first_name,
            {_NAME_EXPR.format(col='middle_name')}              AS middle_name,
            {_NAME_EXPR.format(col='last_name')}                AS last_name,
            {_DOB_EXPR.format(col='date_of_birth')}             AS date_of_birth,
            {_GENDER_EXPR.format(col='gender')}                 AS gender,
            {_ADDR_EXPR.format(col='address_full')}             AS address_full,
            {_ADDR_EXPR.format(col='address_street_number')}    AS address_street_number,
            {_ADDR_EXPR.format(col='address_street_name')}      AS address_street_name,
            {_ADDR_EXPR.format(col='address_town_or_suburb')}   AS address_town_or_suburb,
            {_ADDR_EXPR.format(col='address_lga')}              AS address_lga
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
