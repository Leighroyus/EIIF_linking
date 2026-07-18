from __future__ import annotations

import duckdb

# Fields for which we compute frequency distributions.
# These are used during scoring as the "unmatched probability" (UP).
_PROP_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",
    "gender",
]

# Minimum proportion floor — prevents log-odds from going to ±infinity.
MIN_PROP = 0.0001


def run(conn: duckdb.DuckDBPyConnection) -> None:
    """Build per-field frequency tables across the combined A + B population."""
    conn.execute("""
        CREATE OR REPLACE VIEW lnk.combined AS
        SELECT first_name, middle_name, last_name, date_of_birth, gender
        FROM lnk.dataset_a
        UNION ALL
        SELECT first_name, middle_name, last_name, date_of_birth, gender
        FROM lnk.dataset_b
    """)

    for field in _PROP_FIELDS:
        conn.execute(f"""
            CREATE OR REPLACE TABLE lnk.prop_{field} AS
            WITH counts AS (
                SELECT
                    {field} AS value,
                    COUNT(*) AS cnt
                FROM lnk.combined
                WHERE {field} IS NOT NULL AND {field} != ''
                GROUP BY {field}
            ),
            total AS (SELECT SUM(cnt) AS n FROM counts)
            SELECT
                value,
                cnt,
                GREATEST(cnt * 1.0 / total.n, {MIN_PROP}) AS prop
            FROM counts, total
        """)
