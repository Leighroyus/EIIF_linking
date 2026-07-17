from __future__ import annotations

import duckdb

from ..config import LinkageConfig
from ..schema import JW_FULL_MATCH, JW_PARTIAL_MATCH

# Minimum UP floor (prevents log-odds divergence for extremely rare values).
_MIN_UP = 0.0001
# Maximum UP cap (prevents common values from producing negative match weights).
_MAX_UP = 0.50


def _jw_weight_expr(
    field: str,
    mp: float,
    jw_col: str,
    a_col: str,
    b_col: str,
    up_col: str,
) -> str:
    """
    SQL CASE expression for a fuzzy-scored string field.

    Logic (Fellegi-Sunter log-odds):
      - Either record NULL          → 0  (no evidence either way)
      - JW >= JW_FULL_MATCH         → log2(mp / up)           full match weight
      - JW_PARTIAL <= JW < FULL     → linearly interpolated   partial match weight
      - JW < JW_PARTIAL_MATCH       → log2((1-mp) / (1-up))   disagree weight
    """
    jw_range = JW_FULL_MATCH - JW_PARTIAL_MATCH  # 0.17
    return f"""
        CASE
            WHEN {a_col} IS NULL OR {b_col} IS NULL THEN 0.0
            WHEN {jw_col} >= {JW_FULL_MATCH}
                THEN LOG2({mp} / GREATEST(LEAST({up_col}, {_MAX_UP}), {_MIN_UP}))
            WHEN {jw_col} >= {JW_PARTIAL_MATCH}
                THEN (({jw_col} - {JW_PARTIAL_MATCH}) / {jw_range})
                     * LOG2({mp} / GREATEST(LEAST({up_col}, {_MAX_UP}), {_MIN_UP}))
            ELSE
                LOG2({1 - mp} / (1 - GREATEST(LEAST({up_col}, {_MAX_UP}), {_MIN_UP})))
        END
    """.strip()


def _exact_weight_expr(
    mp: float,
    a_col: str,
    b_col: str,
    up_col: str,
) -> str:
    """SQL CASE expression for an exact-match field (gender, postcode)."""
    return f"""
        CASE
            WHEN {a_col} IS NULL OR {b_col} IS NULL THEN 0.0
            WHEN {a_col} = {b_col}
                THEN LOG2({mp} / GREATEST(LEAST({up_col}, {_MAX_UP}), {_MIN_UP}))
            ELSE
                LOG2({1 - mp} / (1 - GREATEST(LEAST({up_col}, {_MAX_UP}), {_MIN_UP})))
        END
    """.strip()


def _dob_weight_expr(mp: float) -> str:
    """
    DOB scoring uses the date_of_birth proportion table for UP, plus a JW
    similarity pre-computed in pair_data as jw_dob.  An exact DOB is very
    selective (low UP), so it contributes a large positive weight when matched.
    Column names a_dob, b_dob, jw_dob are from the pair_data / with_props CTE.
    """
    return f"""
        CASE
            WHEN a_dob IS NULL OR b_dob IS NULL THEN 0.0
            WHEN a_dob = b_dob
                THEN LOG2({mp} / GREATEST(LEAST(dob_up, {_MAX_UP}), {_MIN_UP}))
            WHEN jw_dob >= 0.85
                THEN (jw_dob - 0.85) / 0.15
                     * LOG2({mp} / GREATEST(LEAST(dob_up, {_MAX_UP}), {_MIN_UP}))
            ELSE
                LOG2({1 - mp} / (1 - GREATEST(LEAST(dob_up, {_MAX_UP}), {_MIN_UP})))
        END
    """.strip()


def run(conn: duckdb.DuckDBPyConnection, config: LinkageConfig) -> None:
    """
    Score every candidate pair using Fellegi-Sunter log-odds weights.

    Each field independently contributes a weight:
      Positive  → evidence the records are the same person
      Negative  → evidence they are different people
      Zero      → field absent in one/both records (no evidence)

    The total_weight is the sum of all field weights.
    """
    mp = config.match_probabilities

    conn.execute(f"""
        CREATE OR REPLACE TABLE wrk.scored_pairs AS
        WITH pair_data AS (
            SELECT
                cp.a_id,
                cp.b_id,
                a.first_name  AS a_fn,  b.first_name  AS b_fn,
                a.middle_name AS a_mn,  b.middle_name AS b_mn,
                a.last_name   AS a_ln,  b.last_name   AS b_ln,
                a.date_of_birth AS a_dob, b.date_of_birth AS b_dob,
                a.gender      AS a_gender, b.gender    AS b_gender,
                a.address_suburb AS a_suburb, b.address_suburb AS b_suburb,
                jaro_winkler_similarity(COALESCE(a.first_name,''),    COALESCE(b.first_name,''))    AS jw_fn,
                jaro_winkler_similarity(COALESCE(a.last_name,''),     COALESCE(b.last_name,''))     AS jw_ln,
                jaro_winkler_similarity(COALESCE(a.middle_name,''),   COALESCE(b.middle_name,''))   AS jw_mn,
                jaro_winkler_similarity(COALESCE(a.date_of_birth,''), COALESCE(b.date_of_birth,'')) AS jw_dob,
                jaro_winkler_similarity(COALESCE(a.address_suburb,''), COALESCE(b.address_suburb,'')) AS jw_suburb
            FROM wrk.candidate_pairs cp
            INNER JOIN lnk.dataset_a a ON a.id = cp.a_id
            INNER JOIN lnk.dataset_b b ON b.id = cp.b_id
        ),
        with_props AS (
            SELECT
                pd.*,
                LEAST(
                    COALESCE(pfna.prop, {_MIN_UP}),
                    COALESCE(pfnb.prop, {_MIN_UP})
                ) AS fn_up,
                LEAST(
                    COALESCE(pmna.prop, {_MIN_UP}),
                    COALESCE(pmnb.prop, {_MIN_UP})
                ) AS mn_up,
                LEAST(
                    COALESCE(plna.prop, {_MIN_UP}),
                    COALESCE(plnb.prop, {_MIN_UP})
                ) AS ln_up,
                LEAST(
                    COALESCE(pdba.prop, {_MIN_UP}),
                    COALESCE(pdbb.prop, {_MIN_UP})
                ) AS dob_up,
                LEAST(
                    COALESCE(pgna.prop, {_MIN_UP}),
                    COALESCE(pgnb.prop, {_MIN_UP})
                ) AS gender_up
            FROM pair_data pd
            LEFT JOIN lnk.prop_first_name  pfna ON pfna.value = pd.a_fn
            LEFT JOIN lnk.prop_first_name  pfnb ON pfnb.value = pd.b_fn
            LEFT JOIN lnk.prop_middle_name pmna ON pmna.value = pd.a_mn
            LEFT JOIN lnk.prop_middle_name pmnb ON pmnb.value = pd.b_mn
            LEFT JOIN lnk.prop_last_name   plna ON plna.value = pd.a_ln
            LEFT JOIN lnk.prop_last_name   plnb ON plnb.value = pd.b_ln
            LEFT JOIN lnk.prop_date_of_birth pdba ON pdba.value = pd.a_dob
            LEFT JOIN lnk.prop_date_of_birth pdbb ON pdbb.value = pd.b_dob
            LEFT JOIN lnk.prop_gender      pgna ON pgna.value = pd.a_gender
            LEFT JOIN lnk.prop_gender      pgnb ON pgnb.value = pd.b_gender
        )
        SELECT
            a_id,
            b_id,
            -- Individual field weights
            {_jw_weight_expr('first_name',    mp.get('first_name', 0.90),    'jw_fn',     'a_fn',     'b_fn',     'fn_up')}     AS wgt_first_name,
            {_jw_weight_expr('middle_name',   mp.get('middle_name', 0.85),   'jw_mn',     'a_mn',     'b_mn',     'mn_up')}     AS wgt_middle_name,
            {_jw_weight_expr('last_name',     mp.get('last_name', 0.92),     'jw_ln',     'a_ln',     'b_ln',     'ln_up')}     AS wgt_last_name,
            {_dob_weight_expr(mp.get('date_of_birth', 0.95))}                                                                    AS wgt_dob,
            {_exact_weight_expr(mp.get('gender', 0.98),     'a_gender',  'b_gender',  'gender_up')}                             AS wgt_gender,
            -- Address suburb: fixed UP (addresses are locally unique; no global freq table)
            CASE
                WHEN a_suburb IS NULL OR b_suburb IS NULL THEN 0.0
                WHEN jw_suburb >= {JW_FULL_MATCH}
                    THEN LOG2({mp.get('address_suburb', 0.82)} / 0.005)
                WHEN jw_suburb >= {JW_PARTIAL_MATCH}
                    THEN (jw_suburb - {JW_PARTIAL_MATCH}) / {JW_FULL_MATCH - JW_PARTIAL_MATCH}
                         * LOG2({mp.get('address_suburb', 0.82)} / 0.005)
                ELSE 0.0
            END AS wgt_suburb,
            -- Similarities exposed for result output
            jw_fn, jw_ln, jw_mn, jw_dob, jw_suburb,
            a_fn AS a_first_name,  a_ln AS a_last_name,  a_mn AS a_middle_name,
            a_dob AS a_dob,  a_gender AS a_gender,
            b_fn AS b_first_name,  b_ln AS b_last_name,  b_mn AS b_middle_name,
            b_dob AS b_dob,  b_gender AS b_gender
        FROM with_props
    """)

    # Compute total_weight as a single derived column for convenience.
    conn.execute("""
        CREATE OR REPLACE TABLE wrk.scored_pairs AS
        SELECT
            *,
            wgt_first_name + wgt_middle_name + wgt_last_name
            + wgt_dob + wgt_gender + wgt_suburb AS total_weight
        FROM wrk.scored_pairs
    """)
