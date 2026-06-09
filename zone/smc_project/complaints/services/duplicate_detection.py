from __future__ import annotations

import re
from datetime import timedelta
from difflib import SequenceMatcher

from django.utils import timezone

from complaints.models import Complaint

# Tuning knobs (0.0 to 1.0)
EXACT_DESC_THRESHOLD = 0.90
EXACT_SUBCAT_THRESHOLD = 0.80
SIMILAR_COMBINED_THRESHOLD = 0.65
DAYS_LOOKBACK = 60

WEIGHT_DESC = 0.60
WEIGHT_SUBCATEGORY = 0.25
WEIGHT_LOCATION = 0.15


def _normalize(text: str) -> str:
    if not text:
        return ""
    value = text.lower().strip()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def detect_duplicates(form_data: dict, exclude_complaint_id: int | None = None) -> dict:
    """
    Compare incoming complaint data against recent complaints.

    Returns dict with keys:
    - is_exact
    - is_similar
    - exact_matches
    - similar_matches
    - matches
    - best_score
    """
    category = (form_data.get("category") or "").strip()
    subcategory = (form_data.get("subcategory") or "").strip()
    zone = (form_data.get("zone") or "").strip()
    location = (form_data.get("location") or "").strip()
    description = (form_data.get("description") or "").strip()

    if not category or not zone or not description:
        return _empty_result()

    cutoff = timezone.now() - timedelta(days=DAYS_LOOKBACK)

    queryset = Complaint.objects.filter(
        category=category,
        zone=zone,
        complaint_date__gte=cutoff,
    ).exclude(status="Resolved")

    if exclude_complaint_id:
        queryset = queryset.exclude(complaint_id=exclude_complaint_id)

    exact_matches = []
    similar_matches = []

    for candidate in queryset:
        desc_score = _similarity(description, candidate.description)
        subcat_score = _similarity(subcategory, candidate.subcategory)
        location_score = _similarity(location, candidate.location)

        combined_score = (
            (desc_score * WEIGHT_DESC)
            + (subcat_score * WEIGHT_SUBCATEGORY)
            + (location_score * WEIGHT_LOCATION)
        )

        item = {
            "complaint": candidate,
            "similarity_score": round(combined_score * 100, 1),
            "desc_score": round(desc_score * 100, 1),
            "match_type": "similar",
        }

        if desc_score >= EXACT_DESC_THRESHOLD and subcat_score >= EXACT_SUBCAT_THRESHOLD:
            item["match_type"] = "exact"
            exact_matches.append(item)
        elif combined_score >= SIMILAR_COMBINED_THRESHOLD:
            similar_matches.append(item)

    exact_matches.sort(key=lambda row: row["similarity_score"], reverse=True)
    similar_matches.sort(key=lambda row: row["similarity_score"], reverse=True)

    matches = exact_matches[:1] + similar_matches[:3]

    return {
        "is_exact": bool(exact_matches),
        "is_similar": bool(similar_matches),
        "exact_matches": exact_matches[:1],
        "similar_matches": similar_matches[:3],
        "matches": matches,
        "best_score": matches[0]["similarity_score"] if matches else 0.0,
    }


def _empty_result() -> dict:
    return {
        "is_exact": False,
        "is_similar": False,
        "exact_matches": [],
        "similar_matches": [],
        "matches": [],
        "best_score": 0.0,
    }
