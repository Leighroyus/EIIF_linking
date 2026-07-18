from __future__ import annotations

import duckdb

from ..config import BlockingConfig


def run(conn: duckdb.DuckDBPyConnection, config: BlockingConfig) -> None:
    """
    Generate candidate A×B pairs via multiple blocking rules, then apply
    a fuzzy-similarity gate to discard obvious non-matches.

    Blocking rules:
      Rule 1 (chunked) — last_name 3-char prefix + first_name initial
      Rule 2           — exact first_name + exact date_of_birth  (handles surname changes)
      Rule 3           — exact last_name + DOB year+month        (handles first-name variations)
      Rule 4           — first_name + last_name (no DOB required, for sparse DOB data)

    Each rule is tagged with its rule number so the fuzzy gate can apply
    different thresholds: DOB-anchored rules are allowed lower name similarity
    since an exact DOB is itself strong evidence.
    """
    conn.execute("DROP TABLE IF EXISTS wrk.raw_candidates")
    conn.execute("""
        CREATE TABLE wrk.raw_candidates (
            a_id VARCHAR,
            b_id VARCHAR,
            block_rule TINYINT
        )
    """)

    # Rule 1: last-name prefix + first-name initial, alphabet-chunked.
    for chunk in config.alphabet_chunks:
        letters = list(chunk.upper())
        like_parts = " OR ".join(f"a.last_name LIKE '{ltr}%'" for ltr in letters)
        conn.execute(f"""
            INSERT INTO wrk.raw_candidates
            SELECT DISTINCT a.id, b.id, 1
            FROM lnk.dataset_a a
            INNER JOIN lnk.dataset_b b
                ON LEFT(a.last_name, 3) = LEFT(b.last_name, 3)
                AND LEFT(COALESCE(a.first_name, ''), 1) = LEFT(COALESCE(b.first_name, ''), 1)
            WHERE ({like_parts})
        """)

    # Rule 2: exact first_name + exact DOB.
    conn.execute("""
        INSERT INTO wrk.raw_candidates
        SELECT DISTINCT a.id, b.id, 2
        FROM lnk.dataset_a a
        INNER JOIN lnk.dataset_b b
            ON a.first_name = b.first_name
            AND a.date_of_birth IS NOT NULL
            AND b.date_of_birth IS NOT NULL
            AND a.date_of_birth = b.date_of_birth
    """)

    # Rule 3: exact last_name + DOB year + DOB month.
    conn.execute("""
        INSERT INTO wrk.raw_candidates
        SELECT DISTINCT a.id, b.id, 3
        FROM lnk.dataset_a a
        INNER JOIN lnk.dataset_b b
            ON a.last_name = b.last_name
            AND a.date_of_birth IS NOT NULL
            AND b.date_of_birth IS NOT NULL
            AND LEFT(a.date_of_birth, 6) = LEFT(b.date_of_birth, 6)
    """)

    # Rule 4: exact first_name + last_name (fallback for missing DOB).
    conn.execute("""
        INSERT INTO wrk.raw_candidates
        SELECT DISTINCT a.id, b.id, 4
        FROM lnk.dataset_a a
        INNER JOIN lnk.dataset_b b
            ON a.first_name = b.first_name
            AND a.last_name = b.last_name
    """)

    # Fuzzy gate: keep pairs that meet minimum name similarity per rule.
    # DOB-anchored rules (2, 3) use a looser last-name threshold to allow
    # for surname changes, maiden names, etc.
    fuzzy_min = config.fuzzy_name_min
    fuzzy_min_dob_rule = max(0.60, fuzzy_min - 0.20)

    conn.execute(f"""
        CREATE OR REPLACE TABLE wrk.candidate_pairs AS
        SELECT DISTINCT rc.a_id, rc.b_id
        FROM wrk.raw_candidates rc
        INNER JOIN lnk.dataset_a a ON a.id = rc.a_id
        INNER JOIN lnk.dataset_b b ON b.id = rc.b_id
        WHERE
            -- Rule 1 + 4: both names must meet the standard threshold
            (rc.block_rule IN (1, 4)
                AND jaro_winkler_similarity(COALESCE(a.last_name, ''), COALESCE(b.last_name, '')) >= {fuzzy_min}
                AND jaro_winkler_similarity(COALESCE(a.first_name, ''), COALESCE(b.first_name, '')) >= {fuzzy_min}
            )
            OR
            -- Rule 2 (first_name+DOB): relax last-name threshold
            (rc.block_rule = 2
                AND jaro_winkler_similarity(COALESCE(a.last_name, ''), COALESCE(b.last_name, '')) >= {fuzzy_min_dob_rule}
            )
            OR
            -- Rule 3 (last_name+DOB): relax first-name threshold
            (rc.block_rule = 3
                AND jaro_winkler_similarity(COALESCE(a.first_name, ''), COALESCE(b.first_name, '')) >= {fuzzy_min_dob_rule}
            )
    """)
    conn.execute("DROP TABLE wrk.raw_candidates")
