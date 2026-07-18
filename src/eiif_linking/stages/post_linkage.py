from __future__ import annotations

import duckdb

from ..config import LinkageConfig
from ..schema import CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD


def run(conn: duckdb.DuckDBPyConnection, config: LinkageConfig) -> None:
    """
    Filter scored pairs, rank matches per A record, and write the final
    linkage result table.

    Output columns (out.linkage_results):
      a_id, b_id
      a_first_name, a_last_name, a_middle_name, a_dob, a_gender
      b_first_name, b_last_name, b_middle_name, b_dob, b_gender
      total_weight
      confidence         — HIGH / MEDIUM / LOW
      is_best_match      — TRUE for the highest-scoring B match per A record
      match_rank         — 1 = best match, 2 = second best, …
      sim_first_name, sim_last_name, sim_middle_name, sim_dob, sim_suburb
      wgt_first_name, wgt_last_name, wgt_middle_name, wgt_dob, wgt_gender, wgt_suburb
    """
    thresholds = config.thresholds
    jw_fn_min = thresholds.jw_first_name_min
    jw_ln_min = thresholds.jw_last_name_min
    total_min = thresholds.total_weight_min
    conf_high = thresholds.confidence_high
    conf_med = thresholds.confidence_medium
    max_matches = thresholds.max_matches_per_a_record

    # QUALIFY must live in the same SELECT that computes the window function.
    qualify_clause = (
        f"QUALIFY ROW_NUMBER() OVER (PARTITION BY sp.a_id ORDER BY sp.total_weight DESC) <= {max_matches}"
        if max_matches is not None else ""
    )

    conn.execute(f"""
        CREATE OR REPLACE TABLE out.linkage_results AS
        WITH ranked AS (
            SELECT
                sp.a_id,
                sp.b_id,
                sp.a_first_name,
                sp.a_middle_name,
                sp.a_last_name,
                sp.a_dob,
                sp.a_gender,
                a.address_suburb AS a_suburb,
                a.address_state  AS a_state,
                sp.b_first_name,
                sp.b_middle_name,
                sp.b_last_name,
                sp.b_dob,
                sp.b_gender,
                b.address_suburb AS b_suburb,
                b.address_state  AS b_state,
                ROUND(sp.total_weight, 4) AS total_weight,
                CASE
                    WHEN sp.total_weight >= {conf_high}  THEN 'HIGH'
                    WHEN sp.total_weight >= {conf_med}   THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS confidence,
                ROW_NUMBER() OVER (
                    PARTITION BY sp.a_id
                    ORDER BY sp.total_weight DESC
                ) AS match_rank,
                ROUND(sp.jw_fn,     4) AS sim_first_name,
                ROUND(sp.jw_ln,     4) AS sim_last_name,
                ROUND(sp.jw_mn,     4) AS sim_middle_name,
                ROUND(sp.jw_dob,    4) AS sim_dob,
                ROUND(sp.wgt_first_name,  4) AS wgt_first_name,
                ROUND(sp.wgt_middle_name, 4) AS wgt_middle_name,
                ROUND(sp.wgt_last_name,   4) AS wgt_last_name,
                ROUND(sp.wgt_dob,         4) AS wgt_dob,
                ROUND(sp.wgt_gender,      4) AS wgt_gender,
                ROUND(sp.wgt_suburb,      4) AS wgt_suburb
            FROM wrk.scored_pairs sp
            INNER JOIN lnk.dataset_a a ON a.id = sp.a_id
            INNER JOIN lnk.dataset_b b ON b.id = sp.b_id
            WHERE sp.total_weight >= {total_min}
              AND sp.jw_fn >= {jw_fn_min}
              AND sp.jw_ln >= {jw_ln_min}
            {qualify_clause}
        )
        SELECT
            *,
            match_rank = 1 AS is_best_match
        FROM ranked
    """)
