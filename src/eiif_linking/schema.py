from __future__ import annotations

# Ordered list of all standard field names used throughout the pipeline.
STANDARD_FIELDS: list[str] = [
    "id",
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",          # normalised to YYYYMMDD string
    "gender",                 # normalised to M / F / None
    "address_full",           # free-text full address (parsed if component fields absent)
    "address_street_number",  # e.g. "42", "5A", "12/34"
    "address_street_name",    # e.g. "HIGH STREET"
    "address_town_or_suburb", # e.g. "FITZROY"
    "address_lga",            # Local Government Area, e.g. "CITY OF MELBOURNE"
]

# These must be resolvable for a record to participate in linkage.
REQUIRED_FIELDS: frozenset[str] = frozenset({"id", "first_name", "last_name"})

# Fields that produce scoring weights when present.
SCOREABLE_FIELDS: list[str] = [
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",
    "gender",
    "address_street_number",
    "address_street_name",
    "address_town_or_suburb",
    "address_lga",
]

# String-similarity fields (Jaro-Winkler); others use exact match.
FUZZY_FIELDS: frozenset[str] = frozenset({
    "first_name", "middle_name", "last_name",
    "address_street_name", "address_town_or_suburb",
})

# Similarity thresholds for JW matching.
JW_FULL_MATCH: float = 0.92
JW_PARTIAL_MATCH: float = 0.75

# Default P(agree | same person) per field.
DEFAULT_MATCH_PROBS: dict[str, float] = {
    "first_name": 0.90,
    "middle_name": 0.85,
    "last_name": 0.92,
    "date_of_birth": 0.95,
    "gender": 0.98,
    "address_street_number": 0.90,
    "address_street_name": 0.85,
    "address_town_or_suburb": 0.80,
    "address_lga": 0.75,
}

# Confidence band boundaries (applied to total_weight in results).
CONFIDENCE_HIGH_THRESHOLD: float = 30.0
CONFIDENCE_MEDIUM_THRESHOLD: float = 20.0
CONFIDENCE_LOW_THRESHOLD: float = 15.0
