"""
Configuration settings for xMatch Entity Resolution pipeline.
"""

from dataclasses import dataclass


@dataclass
class FalkorDBConfig:
    host: str = "localhost"
    port: int = 6379
    graph_name: str = "xmatch_identity_graph"


@dataclass
class SimilarityWeights:
    name_weight: float = 0.45
    email_weight: float = 0.40
    phone_weight: float = 0.15

    # Match thresholds
    link_merge_threshold: float = 0.65  # Minimum score to insert an identity graph edge
    direct_match_high_confidence: float = 0.85
    family_penalty_threshold: float = 0.35  # First name mismatch penalty when surname matches


SAMPLE_RECORDS = [
    {"id": 1, "name": "kaan", "email": "kpapaz@gmail", "phone": "2696227"},
    {"id": 2, "name": "kkaramete", "email": "kalles@gmail.com", "phone": "5182696226"},
    {"id": 3, "name": "kaan karamete", "email": "kallespapaz@gmail", "phone": "404356789"},
    {"id": 4, "name": "gulgun karamete", "email": "gkaramete@kmail.com", "phone": "2696777"},
]

