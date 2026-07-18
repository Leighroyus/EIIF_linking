from __future__ import annotations

# Ordered list of all standard field names used throughout the pipeline.
STANDARD_FIELDS: list[str] = [
    "id",
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",   # normalised to YYYYMMDD string
    "gender",          # normalised to M / F / None
    "address_line1",
    "address_suburb",
    "address_state",
    "postcode",
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
    "address_suburb",
]

# String-similarity fields (Jaro-Winkler); others use exact match.
FUZZY_FIELDS: frozenset[str] = frozenset({"first_name", "middle_name", "last_name", "address_suburb"})

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
    "address_suburb": 0.82,
}

# Confidence band boundaries (applied to total_weight in results).
CONFIDENCE_HIGH_THRESHOLD: float = 30.0
CONFIDENCE_MEDIUM_THRESHOLD: float = 20.0
