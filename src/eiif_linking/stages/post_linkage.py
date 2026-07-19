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
      a_first_name, a_middle_name, a_last_name, a_dob, a_gender
      a_street_number, a_street_name, a_town_or_suburb, a_lga
      b_first_name, b_middle_name, b_last_name, b_dob, b_gender
      b_street_number, b_street_name, b_town_or_suburb, b_lga
      total_weight
      confidence         — HIGH / MEDIUM / LOW
      match_rank         — 1 = best match, 2 = second best, …
      is_best_match      — TRUE for match_rank = 1
      sim_first_name, sim_last_name, sim_middle_name, sim_dob
      sim_street_name, sim_town_or_suburb
      wgt_first_name, wgt_last_name, wgt_middle_name, wgt_dob, wgt_gender
      wgt_address_street_number, wgt_address_street_name,
      wgt_address_town_or_suburb, wgt_address_lga
    """
    thresholds = config.thresholds
    jw_fn_min = thresholds.jw_first_name_min
    jw_ln_min = thresholds.jw_last_name_min
    total_min = thresholds.total_weight_min
    conf_high = thresholds.confidence_high
    conf_med = thresholds.confidence_medium
    conf_low = thresholds.confidence_low
    max_matches = thresholds.max_matches_per_a_record

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
                -- A-side person fields
                sp.a_first_name,
                sp.a_middle_name,
                sp.a_last_name,
                sp.a_dob,
                sp.a_gender,
                -- A-side address fields (from normalised dataset)
                a.address_street_number  AS a_street_number,
                a.address_street_name    AS a_street_name,
                a.address_town_or_suburb AS a_town_or_suburb,
                a.address_lga            AS a_lga,
                -- B-side person fields
                sp.b_first_name,
                sp.b_middle_name,
                sp.b_last_name,
                sp.b_dob,
                sp.b_gender,
                -- B-side address fields
                b.address_street_number  AS b_street_number,
                b.address_street_name    AS b_street_name,
                b.address_town_or_suburb AS b_town_or_suburb,
                b.address_lga            AS b_lga,
                -- Match quality
                ROUND(sp.total_weight, 4) AS total_weight,
                CASE
                    WHEN sp.total_weight >= {conf_high} THEN 'HIGH'
                    WHEN sp.total_weight >= {conf_med}  THEN 'MEDIUM'
                    WHEN sp.total_weight >= {conf_low}  THEN 'LOW'
                    ELSE 'LOW'
                END AS confidence,
                ROW_NUMBER() OVER (
                    PARTITION BY sp.a_id
                    ORDER BY sp.total_weight DESC
                ) AS match_rank,
                -- Similarity scores
                ROUND(sp.jw_fn,          4) AS sim_first_name,
                ROUND(sp.jw_ln,          4) AS sim_last_name,
                ROUND(sp.jw_mn,          4) AS sim_middle_name,
                ROUND(sp.jw_dob,         4) AS sim_dob,
                ROUND(sp.jw_street_name, 4) AS sim_street_name,
                ROUND(sp.jw_town,        4) AS sim_town_or_suburb,
                -- Field weights
                ROUND(sp.wgt_first_name,              4) AS wgt_first_name,
                ROUND(sp.wgt_middle_name,             4) AS wgt_middle_name,
                ROUND(sp.wgt_last_name,               4) AS wgt_last_name,
                ROUND(sp.wgt_dob,                     4) AS wgt_dob,
                ROUND(sp.wgt_gender,                  4) AS wgt_gender,
                ROUND(sp.wgt_address_street_number,   4) AS wgt_address_street_number,
                ROUND(sp.wgt_address_street_name,     4) AS wgt_address_street_name,
                ROUND(sp.wgt_address_town_or_suburb,  4) AS wgt_address_town_or_suburb,
                ROUND(sp.wgt_address_lga,             4) AS wgt_address_lga
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
