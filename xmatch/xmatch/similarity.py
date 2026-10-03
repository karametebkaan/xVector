"""
High-performance similarity metrics for Name, Email, and Phone entity attributes.
Combines RapidFuzz C++ algorithms with domain-specific identity heuristics:
- Jaro-Winkler and Levenshtein metrics
- Token containment and Initial + Surname matching
- Email username subword and prefix/suffix containment
- Phone number normalization, 7-digit suffix matching, and edit distance
- Explainable match reasons and family/household penalty logic
"""

import re
from typing import Dict, Any, List, Tuple
from rapidfuzz import distance, fuzz


def normalize_string(s: str) -> str:
    """Lowercase and strip whitespace and non-alphanumeric characters (except spaces)."""
    if not s:
        return ""
    return re.sub(r"[^\w\s]", "", s.strip().lower())


def extract_email_parts(email: str) -> Tuple[str, str]:
    """Extract username and domain from an email address."""
    if not email:
        return "", ""
    email = email.strip().lower()
    if "@" in email:
        parts = email.split("@", 1)
        return parts[0], parts[1]
    return email, ""


def normalize_phone(phone: str) -> str:
    """Extract digits only from phone number string."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def name_similarity(name1: str, name2: str) -> Tuple[float, List[str], bool]:
    """
    Compute similarity between two names.
    Returns (score: float, reasons: List[str], is_family_conflict: bool).
    """
    n1 = normalize_string(name1)
    n2 = normalize_string(name2)

    if not n1 or not n2:
        return 0.0, ["missing_name"], False

    if n1 == n2:
        return 1.0, ["exact_name_match"], False

    tokens1 = n1.split()
    tokens2 = n2.split()

    reasons = []

    # 1. Token containment (e.g. "kaan" in "kaan karamete")
    set1, set2 = set(tokens1), set(tokens2)
    if set1.issubset(set2) or set2.issubset(set1):
        min_len = min(len(set1), len(set2))
        max_len = max(len(set1), len(set2))
        containment_score = 0.85 + 0.15 * (min_len / max_len)
        reasons.append(f"token_containment({' '.join(tokens1)} in {' '.join(tokens2)})")
        return containment_score, reasons, False

    # 2. Initial + Surname match (e.g. "kkaramete" vs "kaan karamete")
    # Check if one is a single compact handle: initial + last_name
    for target_compact, target_spaced in [(n1, tokens2), (n2, tokens1)]:
        if len(target_spaced) >= 2:
            first_init = target_spaced[0][0]
            last_name = target_spaced[-1]
            compact_last = target_compact[1:] if len(target_compact) > 1 else ""
            compact_init = target_compact[0] if target_compact else ""
            
            # Exact initial + last name
            if target_compact == f"{first_init}{last_name}":
                reasons.append(f"initial_surname_match({first_init}+{last_name} == {target_compact})")
                return 0.92, reasons, False
            # Matching surname but conflicting initial (e.g. kkaramete vs gulgun karamete)
            elif compact_last == last_name and compact_init != first_init:
                reasons.append(f"family_surname_shared({last_name}), but conflicting_initial({compact_init} vs {first_init})")
                return 0.30, reasons, True

    # 3. Check for Surname match with distinct first names (Family conflict check)
    # E.g. "gulgun karamete" vs "kaan karamete"
    if len(tokens1) >= 2 and len(tokens2) >= 2:
        last1, last2 = tokens1[-1], tokens2[-1]
        first1, first2 = tokens1[0], tokens2[0]

        surname_sim = distance.JaroWinkler.similarity(last1, last2)
        first_sim = distance.JaroWinkler.similarity(first1, first2)

        if surname_sim > 0.85 and first_sim < 0.55:
            # High probability of different family members sharing household
            reasons.append(f"family_surname_shared({last1}), but distinct_first_name({first1} vs {first2})")
            return 0.30, reasons, True  # Penalized score

    # 4. Standard Jaro-Winkler on normalized string
    jw_score = distance.JaroWinkler.similarity(n1, n2)
    token_sort = fuzz.token_sort_ratio(n1, n2) / 100.0

    score = max(jw_score, token_sort)
    if score >= 0.70:
        reasons.append(f"jaro_winkler_name({score:.2f})")

    return score, reasons, False


def email_similarity(email1: str, email2: str) -> Tuple[float, List[str]]:
    """
    Compute similarity between two email addresses.
    Accounts for common subwords, prefix/suffixes, and username roots.
    """
    user1, dom1 = extract_email_parts(email1)
    user2, dom2 = extract_email_parts(email2)

    if not user1 or not user2:
        return 0.0, ["missing_email"]

    if user1 == user2 and dom1 == dom2:
        return 1.0, ["exact_email_match"]

    reasons = []

    # Check username exact match across different/missing domains
    if user1 == user2:
        reasons.append("exact_username_match")
        return 0.90, reasons

    # Substring / Prefix / Suffix containment
    # E.g. "kalles" in "kallespapaz", "papaz" in "kallespapaz"
    shorter, longer = (user1, user2) if len(user1) <= len(user2) else (user2, user1)
    
    # 1. Prefix match (e.g. kalles is prefix of kallespapaz)
    if longer.startswith(shorter) and len(shorter) >= 4:
        ratio = len(shorter) / len(longer)
        score = 0.80 + 0.15 * ratio
        reasons.append(f"email_username_prefix({shorter} in {longer})")
        return score, reasons

    # 2. Substring containment (e.g. papaz in kallespapaz, or kpapaz shares papaz)
    if shorter in longer and len(shorter) >= 4:
        ratio = len(shorter) / len(longer)
        score = 0.75 + 0.15 * ratio
        reasons.append(f"email_username_substring({shorter} in {longer})")
        return score, reasons

    # 3. Subword overlap check: test if shorter without initial is in longer
    # E.g. kpapaz -> papaz in kallespapaz
    if len(shorter) >= 5 and shorter[1:] in longer:
        root = shorter[1:]
        score = 0.82
        reasons.append(f"email_root_subword({root} in {longer})")
        return score, reasons

    # 4. RapidFuzz partial / Levenshtein ratio
    lev_ratio = distance.Levenshtein.normalized_similarity(user1, user2)
    partial_ratio = fuzz.partial_ratio(user1, user2) / 100.0

    score = max(lev_ratio, partial_ratio * 0.85)
    if score >= 0.65:
        reasons.append(f"fuzzy_email_similarity({score:.2f})")

    return score, reasons


def phone_similarity(phone1: str, phone2: str) -> Tuple[float, List[str]]:
    """
    Compute similarity between two phone numbers.
    Normalizes digits and compares local 7-digit suffix and edit distance.
    """
    digits1 = normalize_phone(phone1)
    digits2 = normalize_phone(phone2)

    if not digits1 or not digits2:
        return 0.0, ["missing_phone"]

    if digits1 == digits2:
        return 1.0, ["exact_phone_match"]

    reasons = []

    # Extract last 7 digits (standard North American local line)
    suffix1 = digits1[-7:] if len(digits1) >= 7 else digits1
    suffix2 = digits2[-7:] if len(digits2) >= 7 else digits2

    if suffix1 == suffix2:
        reasons.append(f"matching_7digit_suffix({suffix1})")
        return 0.95, reasons

    # Compute Levenshtein distance on 7-digit suffixes
    # E.g. 2696227 vs 2696226 (distance 1!)
    if len(suffix1) == 7 and len(suffix2) == 7:
        dist = distance.Levenshtein.distance(suffix1, suffix2)
        if dist == 1:
            reasons.append(f"phone_suffix_1digit_diff({suffix1} vs {suffix2})")
            return 0.82, reasons
        elif dist == 2:
            reasons.append(f"phone_suffix_2digit_diff({suffix1} vs {suffix2})")
            return 0.45, reasons

    lev_ratio = distance.Levenshtein.normalized_similarity(digits1, digits2)
    if lev_ratio >= 0.70:
        reasons.append(f"fuzzy_phone_match({lev_ratio:.2f})")
        return lev_ratio * 0.7, reasons

    return 0.0, ["phone_mismatch"]


def compute_pair_similarity(
    r1: Dict[str, Any],
    r2: Dict[str, Any],
    name_wt: float = 0.45,
    email_wt: float = 0.40,
    phone_wt: float = 0.15,
) -> Dict[str, Any]:
    """
    Compute composite similarity confidence between two records.
    Returns dictionary with individual scores, composite score, match reasons, and flags.
    """
    n_score, n_reasons, is_family_conflict = name_similarity(r1.get("name", ""), r2.get("name", ""))
    e_score, e_reasons = email_similarity(r1.get("email", ""), r2.get("email", ""))
    p_score, p_reasons = phone_similarity(r1.get("phone", ""), r2.get("phone", ""))

    # Composite weighted score
    composite = (n_score * name_wt) + (e_score * email_wt) + (p_score * phone_wt)

    # Penalize if family conflict detected
    if is_family_conflict:
        composite = min(composite * 0.5, 0.40)

    # Collect all explainable reasons
    all_reasons = []
    if n_reasons and n_reasons != ["missing_name"]:
        all_reasons.extend(n_reasons)
    if e_reasons and e_reasons != ["missing_email"]:
        all_reasons.extend(e_reasons)
    if p_reasons and p_reasons != ["missing_phone"] and p_reasons != ["phone_mismatch"]:
        all_reasons.extend(p_reasons)

    breakdown = {
        "name": {
            "val1": r1.get("name", ""),
            "val2": r2.get("name", ""),
            "score": round(n_score, 3),
            "weight": name_wt,
            "weighted_contribution": round(n_score * name_wt, 3),
            "primary_rule": n_reasons[0] if n_reasons else "standard_jaro_winkler",
            "all_reasons": n_reasons,
            "is_conflict": is_family_conflict,
        },
        "email": {
            "val1": r1.get("email", ""),
            "val2": r2.get("email", ""),
            "score": round(e_score, 3),
            "weight": email_wt,
            "weighted_contribution": round(e_score * email_wt, 3),
            "primary_rule": e_reasons[0] if e_reasons else "levenshtein_similarity",
            "all_reasons": e_reasons,
        },
        "phone": {
            "val1": r1.get("phone", ""),
            "val2": r2.get("phone", ""),
            "score": round(p_score, 3),
            "weight": phone_wt,
            "weighted_contribution": round(p_score * phone_wt, 3),
            "primary_rule": p_reasons[0] if p_reasons else "phone_mismatch",
            "all_reasons": p_reasons,
        },
        "composite": {
            "name_component": round(n_score * name_wt, 3),
            "email_component": round(e_score * email_wt, 3),
            "phone_component": round(p_score * phone_wt, 3),
            "raw_sum": round((n_score * name_wt) + (e_score * email_wt) + (p_score * phone_wt), 3),
            "final_confidence": round(composite, 3),
            "formula_string": f"({round(n_score, 3)} × {name_wt}) + ({round(e_score, 3)} × {email_wt}) + ({round(p_score, 3)} × {phone_wt})",
            "penalty_applied": is_family_conflict,
            "penalty_note": "Penalized by 50% (capped at 0.40) due to Household/Family first-name conflict" if is_family_conflict else "None",
        },
    }

    return {
        "id1": r1["id"],
        "id2": r2["id"],
        "name_score": round(n_score, 3),
        "email_score": round(e_score, 3),
        "phone_score": round(p_score, 3),
        "composite_confidence": round(composite, 3),
        "is_family_conflict": is_family_conflict,
        "match_reasons": all_reasons,
        "breakdown": breakdown,
    }

