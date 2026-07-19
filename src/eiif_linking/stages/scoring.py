from __future__ import annotations

import duckdb

from ..config import LinkageConfig
from ..schema import JW_FULL_MATCH, JW_PARTIAL_MATCH

_MIN_UP = 0.0001
_MAX_UP = 0.50

# Fixed unmatched-probability (UP) values for address fields.
# These use hardcoded values rather than population frequency tables
# because address distributions are geographically local and a global
# frequency table would systematically over-weight agreement on common
# values (e.g. "HIGH STREET").
_UP_STREET_NUM  = 0.05   # ~1 in 20 unrelated people share the same house number
_UP_STREET_NAME = 0.01   # ~1 in 100 unrelated people live on a same-named street
_UP_TOWN        = 0.02   # ~1 in 50  unrelated people in the same suburb/town
_UP_LGA         = 0.10   # ~1 in 10  unrelated people in the same LGA


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

      - Either record NULL          → 0  (no evidence either way)
      - JW >= JW_FULL_MATCH         → log2(mp / up)           full match weight
      - JW_PARTIAL <= JW < FULL     → linearly interpolated   partial match weight
      - JW < JW_PARTIAL_MATCH       → log2((1-mp) / (1-up))   disagree weight
    """
    jw_range = JW_FULL_MATCH - JW_PARTIAL_MATCH
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
    """SQL CASE expression for an exact-match field (gender)."""
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
    """DOB scoring with exact-match and near-match interpolation."""
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


def _addr_jw_expr(mp: float, jw_col: str, a_col: str, b_col: str, up: float) -> str:
    """
    JW-scored address field with a hardcoded UP.
    Mismatches return 0 (no penalty) — address data is often incomplete or
    stale, so disagreement should not count against a pair.
    """
    jw_range = JW_FULL_MATCH - JW_PARTIAL_MATCH
    match_wgt = f"LOG2({mp} / {up})"
    return f"""
        CASE
            WHEN {a_col} IS NULL OR {b_col} IS NULL THEN 0.0
            WHEN {jw_col} >= {JW_FULL_MATCH}
                THEN {match_wgt}
            WHEN {jw_col} >= {JW_PARTIAL_MATCH}
                THEN (({jw_col} - {JW_PARTIAL_MATCH}) / {jw_range}) * {match_wgt}
            ELSE 0.0
        END
    """.strip()


def _addr_exact_expr(mp: float, a_col: str, b_col: str, up: float) -> str:
    """
    Exact-match address field with a hardcoded UP.
    Mismatches return 0 (no penalty).
    """
    return f"""
        CASE
            WHEN {a_col} IS NULL OR {b_col} IS NULL THEN 0.0
            WHEN {a_col} = {b_col} THEN LOG2({mp} / {up})
            ELSE 0.0
        END
    """.strip()


def run(conn: duckdb.DuckDBPyConnection, config: LinkageConfig) -> None:
    """
    Score every candidate pair using Fellegi-Sunter log-odds weights.

    Each field independently contributes a weight:
      Positive  → evidence the records are the same person
      Negative  → evidence they are different people
      Zero      → field absent in one/both records, or address mismatch
                  (address mismatches are zero rather than negative because
                   address data is frequently incomplete, stale, or
                   inconsistently formatted)

    The total_weight is the sum of all field weights.
    """
    mp = config.match_probabilities

    conn.execute(f"""
        CREATE OR REPLACE TABLE wrk.scored_pairs AS
        WITH pair_data AS (
            SELECT
                cp.a_id,
                cp.b_id,
                -- Person fields
                a.first_name    AS a_fn,   b.first_name    AS b_fn,
                a.middle_name   AS a_mn,   b.middle_name   AS b_mn,
                a.last_name     AS a_ln,   b.last_name     AS b_ln,
                a.date_of_birth AS a_dob,  b.date_of_birth AS b_dob,
                a.gender        AS a_gender, b.gender      AS b_gender,
                -- Address fields
                a.address_street_number  AS a_street_num,
                b.address_street_number  AS b_street_num,
                a.address_street_name    AS a_street_name,
                b.address_street_name    AS b_street_name,
                a.address_town_or_suburb AS a_town,
                b.address_town_or_suburb AS b_town,
                a.address_lga            AS a_lga,
                b.address_lga            AS b_lga,
                -- Jaro-Winkler similarities
                jaro_winkler_similarity(COALESCE(a.first_name,''),    COALESCE(b.first_name,''))    AS jw_fn,
                jaro_winkler_similarity(COALESCE(a.last_name,''),     COALESCE(b.last_name,''))     AS jw_ln,
                jaro_winkler_similarity(COALESCE(a.middle_name,''),   COALESCE(b.middle_name,''))   AS jw_mn,
                jaro_winkler_similarity(COALESCE(a.date_of_birth,''), COALESCE(b.date_of_birth,'')) AS jw_dob,
                jaro_winkler_similarity(COALESCE(a.address_street_name,''),    COALESCE(b.address_street_name,''))    AS jw_street_name,
                jaro_winkler_similarity(COALESCE(a.address_town_or_suburb,''), COALESCE(b.address_town_or_suburb,'')) AS jw_town
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
            LEFT JOIN lnk.prop_first_name   pfna ON pfna.value = pd.a_fn
            LEFT JOIN lnk.prop_first_name   pfnb ON pfnb.value = pd.b_fn
            LEFT JOIN lnk.prop_middle_name  pmna ON pmna.value = pd.a_mn
            LEFT JOIN lnk.prop_middle_name  pmnb ON pmnb.value = pd.b_mn
            LEFT JOIN lnk.prop_last_name    plna ON plna.value = pd.a_ln
            LEFT JOIN lnk.prop_last_name    plnb ON plnb.value = pd.b_ln
            LEFT JOIN lnk.prop_date_of_birth pdba ON pdba.value = pd.a_dob
            LEFT JOIN lnk.prop_date_of_birth pdbb ON pdbb.value = pd.b_dob
            LEFT JOIN lnk.prop_gender       pgna ON pgna.value = pd.a_gender
            LEFT JOIN lnk.prop_gender       pgnb ON pgnb.value = pd.b_gender
        )
        SELECT
            a_id,
            b_id,
            -- Person field weights
            {_jw_weight_expr('first_name',  mp.get('first_name',  0.90), 'jw_fn',  'a_fn', 'b_fn', 'fn_up')}    AS wgt_first_name,
            {_jw_weight_expr('middle_name', mp.get('middle_name', 0.85), 'jw_mn',  'a_mn', 'b_mn', 'mn_up')}    AS wgt_middle_name,
            {_jw_weight_expr('last_name',   mp.get('last_name',   0.92), 'jw_ln',  'a_ln', 'b_ln', 'ln_up')}    AS wgt_last_name,
            {_dob_weight_expr(mp.get('date_of_birth', 0.95))}                                                    AS wgt_dob,
            {_exact_weight_expr(mp.get('gender', 0.98), 'a_gender', 'b_gender', 'gender_up')}                   AS wgt_gender,
            -- Address field weights (no penalty for mismatch — see _addr_*_expr)
            {_addr_exact_expr(mp.get('address_street_number',  0.90), 'a_street_num',  'b_street_num',  _UP_STREET_NUM)}   AS wgt_address_street_number,
            {_addr_jw_expr(   mp.get('address_street_name',   0.85), 'jw_street_name', 'a_street_name', 'b_street_name', _UP_STREET_NAME)} AS wgt_address_street_name,
            {_addr_jw_expr(   mp.get('address_town_or_suburb',0.80), 'jw_town',        'a_town',        'b_town',        _UP_TOWN)}        AS wgt_address_town_or_suburb,
            {_addr_exact_expr(mp.get('address_lga',           0.75), 'a_lga',          'b_lga',         _UP_LGA)}                         AS wgt_address_lga,
            -- Similarities exposed for result output
            jw_fn, jw_ln, jw_mn, jw_dob, jw_street_name, jw_town,
            -- Person field values carried forward for post_linkage output
            a_fn AS a_first_name,  a_ln AS a_last_name,  a_mn AS a_middle_name,
            a_dob, a_gender,
            b_fn AS b_first_name,  b_ln AS b_last_name,  b_mn AS b_middle_name,
            b_dob, b_gender
        FROM with_props
    """)

    conn.execute("""
        CREATE OR REPLACE TABLE wrk.scored_pairs AS
        SELECT
            *,
            wgt_first_name + wgt_middle_name + wgt_last_name
            + wgt_dob + wgt_gender
            + wgt_address_street_number + wgt_address_street_name
            + wgt_address_town_or_suburb + wgt_address_lga
            AS total_weight
        FROM wrk.scored_pairs
    """)
