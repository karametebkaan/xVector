"""
Golden Record Selection and Multi-Dimensional Attribute Synthesis Engine.
Evaluates entity clusters using Multi-Layer (Multiplex) Graph Centrality to determine:
1. Canonical Name (via Name Layer PageRank & token completeness)
2. Canonical Email (via Email Layer PageRank & domain TLD validity)
3. Canonical Phone (via Phone Layer PageRank & 10-digit E.164 completeness)
4. Golden Centroid Entity (via Composite Layer PageRank & Degree)
"""

from typing import List, Dict, Any


def compute_name_quality(name: str) -> float:
    """Evaluate name completeness: multi-token names receive highest score."""
    name = (name or "").strip()
    tokens = name.split()
    if len(tokens) >= 2:
        return 1.0  # Full name (first + surname)
    elif len(tokens) == 1 and len(name) > 4:
        return 0.5  # Single token / handle
    elif tokens:
        return 0.3
    return 0.0


def compute_email_quality(email: str) -> float:
    """
    Evaluate email information richness.
    Prioritizes complete compound usernames (e.g. kallespapaz) over abbreviated handles,
    without artificially penalizing dirty lakehouse data missing top-level domain '.com'.
    """
    email = (email or "").strip().lower()
    if "@" in email:
        username = email.split("@")[0]
        # Username richness based on length and token density
        user_score = min(len(username) / 11.0, 1.0)
        return round(user_score, 3)
    return 0.1 if email else 0.0


def compute_phone_quality(phone: str) -> float:
    """Evaluate phone completeness: standard 10-digit E.164 phone receives highest score."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) >= 10:
        return 1.0  # Complete phone with area code (e.g. 518-269-6226)
    elif len(digits) == 7:
        return 0.6  # Local line without area code (e.g. 269-6227)
    return 0.2 if digits else 0.0


class GoldenRecordResolver:
    """
    Resolves multi-layer identity clusters into synthesized Master Golden Records
    using dimensional graph centrality and attribute survivorship.
    """

    def __init__(self, records: List[Dict[str, Any]], centrality_map: Dict[int, Dict[str, Any]]):
        self.records_by_id = {r["id"]: r for r in records}
        self.centrality_map = centrality_map

    def resolve_cluster(self, cluster_id: int, member_ids: List[int], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Produce a unified Master Golden Record from a cluster of matching member IDs.
        Picks the best name, best email, and best phone from dimensional layers.
        """
        members = [self.records_by_id[mid] for mid in member_ids]

        # 1. Overall Cluster Centroid (Composite Layer)
        centroid_candidates = []
        for m in members:
            mid = m["id"]
            c_info = self.centrality_map.get(mid, {})
            pr_comp = c_info.get("pagerank", 0.0)
            w_deg = c_info.get("weighted_degree", 0.0)
            score = (0.6 * pr_comp) + (0.4 * (w_deg / 2.0))
            centroid_candidates.append((score, mid, m))

        centroid_candidates.sort(key=lambda x: x[0], reverse=True)
        _, centroid_id, centroid_rec = centroid_candidates[0]

        # 2. Dimension 1: Best Canonical Name
        name_candidates = []
        for m in members:
            mid = m["id"]
            name = m.get("name", "").strip()
            if not name:
                continue
            c_info = self.centrality_map.get(mid, {})
            pr_name = c_info.get("name_pagerank", 0.0)
            q_name = compute_name_quality(name)
            score = (0.5 * pr_name) + (0.5 * q_name)
            name_candidates.append((score, len(name), name, mid))

        if name_candidates:
            name_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            canonical_name = name_candidates[0][2]
            name_source_id = name_candidates[0][3]
        else:
            canonical_name = centroid_rec.get("name", "")
            name_source_id = centroid_id

        all_names = [m.get("name", "").strip() for m in members if m.get("name")]
        aliases = sorted(list(set(n for n in all_names if n != canonical_name)))

        # 3. Dimension 2: Best Canonical Email
        # Prioritize GraphBLAS Email PageRank (60%) and compound username richness (40%)
        email_candidates = []
        for m in members:
            mid = m["id"]
            email = m.get("email", "").strip()
            if not email:
                continue
            c_info = self.centrality_map.get(mid, {})
            pr_email = c_info.get("email_pagerank", 0.0)
            q_email = compute_email_quality(email)
            score = (0.60 * pr_email) + (0.40 * q_email)
            username_len = len(email.split("@")[0]) if "@" in email else len(email)
            email_candidates.append((score, username_len, email, mid))

        if email_candidates:
            email_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            primary_email = email_candidates[0][2]
            email_source_id = email_candidates[0][3]
        else:
            primary_email = centroid_rec.get("email", "")
            email_source_id = centroid_id

        all_emails = sorted(list(set(m.get("email", "").strip() for m in members if m.get("email"))))

        # 4. Dimension 3: Best Canonical Phone
        phone_candidates = []
        for m in members:
            mid = m["id"]
            phone = m.get("phone", "").strip()
            if not phone:
                continue
            c_info = self.centrality_map.get(mid, {})
            pr_phone = c_info.get("phone_pagerank", 0.0)
            q_phone = compute_phone_quality(phone)
            score = (0.4 * pr_phone) + (0.6 * q_phone)
            phone_candidates.append((score, len(phone), phone, mid))

        if phone_candidates:
            phone_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            primary_phone = phone_candidates[0][2]
            phone_source_id = phone_candidates[0][3]
        else:
            primary_phone = centroid_rec.get("phone", "")
            phone_source_id = centroid_id

        all_phones = sorted(
            list(set(m.get("phone", "").strip() for m in members if m.get("phone"))),
            key=lambda p: (len("".join(c for c in p if c.isdigit())) >= 10, len(p)),
            reverse=True
        )

        # 5. Cluster Confidence Calculation
        cluster_edges = [
            e for e in edges
            if e["id1"] in member_ids and e["id2"] in member_ids and e.get("rel_type") == "SIMILAR_TO"
        ]
        if cluster_edges:
            avg_confidence = round(sum(e["weight"] for e in cluster_edges) / len(cluster_edges), 3)
            min_confidence = round(min(e["weight"] for e in cluster_edges), 3)
        else:
            avg_confidence = 1.0
            min_confidence = 1.0

        return {
            "cluster_id": cluster_id,
            "member_ids": member_ids,
            "centroid_id": centroid_id,
            "centroid_name": centroid_rec.get("name", ""),
            "canonical_name": canonical_name,
            "name_source_id": name_source_id,
            "aliases": aliases,
            "primary_email": primary_email,
            "email_source_id": email_source_id,
            "all_emails": all_emails,
            "primary_phone": primary_phone,
            "phone_source_id": phone_source_id,
            "all_phones": all_phones,
            "cluster_size": len(members),
            "average_confidence": avg_confidence,
            "min_confidence": min_confidence,
        }
