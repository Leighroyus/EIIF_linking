from __future__ import annotations

"""
Address parsing and LGA enrichment utilities.

parse_address_full()  — extract street_number, street_name, town_or_suburb
                         from a free-text Australian address string
lookup_lga()          — map suburb/town name → LGA name using the bundled
                         data/suburb_lga.csv reference file
enrich_address_df()   — apply both to a whole DataFrame in one pass,
                         filling only missing component fields
"""

import re
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Bundled suburb → LGA reference data
# data/suburb_lga.csv lives two levels above src/eiif_linking/
# ---------------------------------------------------------------------------
_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "suburb_lga.csv"

# Lazy-loaded lookup indices; populated on first call to lookup_lga()
_lga_by_suburb_state: dict[tuple[str, str], str] | None = None
_lga_by_suburb: dict[str, str] | None = None


def _ensure_lga_loaded() -> None:
    global _lga_by_suburb_state, _lga_by_suburb
    if _lga_by_suburb_state is not None:
        return
    if not _DATA_PATH.exists():
        _lga_by_suburb_state = {}
        _lga_by_suburb = {}
        return
    df = pd.read_csv(_DATA_PATH, dtype=str)
    df["suburb"] = df["suburb"].str.upper().str.strip()
    df["state"] = df["state"].str.upper().str.strip()
    df["lga"] = df["lga"].str.upper().str.strip()
    _lga_by_suburb_state = {
        (row["suburb"], row["state"]): row["lga"]
        for _, row in df.iterrows()
    }
    # State-agnostic fallback: first entry for each suburb name wins
    _lga_by_suburb = {}
    for (suburb, _), lga in _lga_by_suburb_state.items():
        if suburb not in _lga_by_suburb:
            _lga_by_suburb[suburb] = lga


def lookup_lga(suburb: Optional[str], state: Optional[str] = None) -> Optional[str]:
    """Return the LGA name for a suburb/town, or None if not found."""
    _ensure_lga_loaded()
    if not suburb:
        return None
    s = str(suburb).upper().strip()
    if state:
        result = _lga_by_suburb_state.get((s, str(state).upper().strip()))
        if result:
            return result
    return _lga_by_suburb.get(s)


# ---------------------------------------------------------------------------
# Address string parser
# ---------------------------------------------------------------------------

# Match trailing postcode/state separated by comma or whitespace (any order).
# Two-pass stripping in _strip_trailing_state_postcode handles both orderings.
_RE_TRAILING_POSTCODE = re.compile(r'[,\s]+\d{4}\s*$')
_RE_TRAILING_STATE = re.compile(
    r'[,\s]+(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s*$', re.IGNORECASE
)
# Matches an optional unit/lot prefix then a street number then street name.
# Handles: "123 Smith St", "Unit 4/56 Main Rd", "5/123 High St",
#           "Lot 2 Old Road", "U3 / 45 Beach Ave"
_RE_STREET = re.compile(
    r'^'
    r'(?:(?:UNIT|APT|FLAT|SUITE|LEVEL|SHOP|U)\s+[\w/-]+[\s,/]+)?'
    r'(?:(?:LOT|RSD|RMB)\s+[\w/-]+\s+)?'
    r'(\d+\w*(?:[/\-]\d+\w*)*)'  # street number: 123, 56-60, 13/56, 13/56-60
    r'\s+'
    r'(.+)',                      # street name group
    re.IGNORECASE,
)


def _strip_trailing_state_postcode(addr: str) -> str:
    """Strip trailing postcode and/or state from a full address string.

    Two passes handle either ordering (e.g. 'NSW 2000' or '2000 NSW') and
    comma-separated components (e.g. 'Springfield, NSW, 2000').
    """
    for _ in range(2):
        addr = _RE_TRAILING_POSTCODE.sub('', addr).strip()
        addr = _RE_TRAILING_STATE.sub('', addr).strip()
    return addr


def _find_suburb_suffix(text: str) -> tuple[Optional[str], Optional[str]]:
    """Identify a suburb at the end of `text` via the bundled LGA lookup.

    Tries trailing word groups of 1–4 words (longest first so multi-word
    suburbs like ALICE SPRINGS are matched before single words). Always
    leaves at least one word remaining for the street component.

    Returns (street_part, suburb) where suburb is None if no match found.
    """
    _ensure_lga_loaded()
    if not _lga_by_suburb:
        return text, None
    words = text.split()
    for n in range(min(4, len(words) - 1), 0, -1):
        candidate = ' '.join(words[-n:])
        if candidate in _lga_by_suburb:
            return ' '.join(words[:-n]), candidate
    return text, None


def parse_address_full(address: str) -> dict[str, Optional[str]]:
    """
    Parse a free-text Australian address string into components.

    Returns dict with keys:
        address_street_number, address_street_name, address_town_or_suburb
    Any component that cannot be extracted is None.
    """
    result: dict[str, Optional[str]] = {
        "address_street_number": None,
        "address_street_name": None,
        "address_town_or_suburb": None,
    }
    if not address or not str(address).strip():
        return result

    addr = str(address).strip().upper()

    # Strip trailing postcode and state *before* splitting on commas so that
    # formats like "Springfield, NSW 2000" and "Springfield, NSW, 2000" both
    # leave "Springfield" as the last comma-separated part.
    addr = _strip_trailing_state_postcode(addr)

    parts = [p.strip() for p in addr.split(',') if p.strip()]

    if len(parts) >= 2:
        street_raw = parts[0]
        town: Optional[str] = parts[-1] or None
    else:
        # No comma: try to identify suburb from the LGA lookup first (handles
        # multi-word suburb names), then fall back to the last single word.
        street_raw, town = _find_suburb_suffix(addr)
        if town is None:
            tokens = addr.split()
            if len(tokens) >= 3:
                street_raw = ' '.join(tokens[:-1])
                town = tokens[-1]
            else:
                street_raw = addr

    if town:
        result["address_town_or_suburb"] = town.strip() or None

    if street_raw:
        m = _RE_STREET.match(street_raw.strip())
        if m:
            result["address_street_number"] = m.group(1).upper()
            result["address_street_name"] = m.group(2).upper().strip() or None
        else:
            cleaned = street_raw.upper().strip()
            result["address_street_name"] = cleaned or None

    return result


# ---------------------------------------------------------------------------
# DataFrame enrichment (called from ingest before SQL normalisation)
# ---------------------------------------------------------------------------

def enrich_address_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing address component columns from address_full, then fill
    missing address_lga from address_town_or_suburb.

    Returns a modified copy. Input column names must be the standard pipeline
    field names. Missing columns are silently added as None.
    """
    df = df.copy()

    for col in (
        "address_full", "address_street_number", "address_street_name",
        "address_town_or_suburb", "address_lga",
    ):
        if col not in df.columns:
            df[col] = None
        # DuckDB returns all-NULL columns as nullable integer (Int64).
        # Cast to object so string values can be assigned without a coercion error.
        if not pd.api.types.is_object_dtype(df[col]):
            df[col] = df[col].astype(object)

    # Parse address_full where street_name is missing and address_full is present
    has_full = df["address_full"].notna() & (df["address_full"].astype(str).str.strip() != "")
    needs_parse = has_full & (
        df["address_street_name"].isna() | (df["address_street_name"].astype(str).str.strip() == "")
    )
    if needs_parse.any():
        parsed = df.loc[needs_parse, "address_full"].map(parse_address_full)
        for field in ("address_street_number", "address_street_name", "address_town_or_suburb"):
            blank = df[field].isna() | (df[field].astype(str).str.strip() == "")
            mask = needs_parse & blank
            if mask.any():
                df.loc[mask, field] = parsed[mask].map(lambda d, f=field: d.get(f))

    # Look up LGA from town_or_suburb where LGA is missing
    has_town = (
        df["address_town_or_suburb"].notna()
        & (df["address_town_or_suburb"].astype(str).str.strip() != "")
    )
    needs_lga = (
        df["address_lga"].isna() | (df["address_lga"].astype(str).str.strip() == "")
    ) & has_town
    if needs_lga.any():
        df.loc[needs_lga, "address_lga"] = (
            df.loc[needs_lga, "address_town_or_suburb"].map(lookup_lga)
        )

    return df
