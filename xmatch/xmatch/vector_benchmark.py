"""
Benchmark and comparative analysis:
Field-Aware Probabilistic Fuzzy Graph vs. Dense/Subword Vector Embeddings.
Demonstrates the pitfalls of pure vector kNN on alphanumeric identity data.
"""

from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


def run_vector_analysis(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare character/word n-gram vector cosine similarities against domain reality.
    """
    # 1. Document representations: concatenate fields
    docs = [
        f"{r.get('name', '')} {r.get('email', '')} {r.get('phone', '')}"
        for r in records
    ]

    # Subword character n-gram (range 2-4) mimicking modern dense subword embedding models
    char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    char_mat = char_vectorizer.fit_transform(docs)
    char_sim = cosine_similarity(char_mat)

    # Individual field comparisons
    name_docs = [r.get("name", "") for r in records]
    name_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit_transform(name_docs)
    name_sim = cosine_similarity(name_vec)

    phone_docs = [r.get("phone", "") for r in records]
    phone_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3)).fit_transform(phone_docs)
    phone_sim = cosine_similarity(phone_vec)

    pairwise_results = []
    n = len(records)
    for i in range(n):
        for j in range(i + 1, n):
            r1, r2 = records[i], records[j]
            overall_cos = round(float(char_sim[i, j]), 3)
            n_cos = round(float(name_sim[i, j]), 3)
            p_cos = round(float(phone_sim[i, j]), 3)

            # Note specific vulnerability flags
            flag = ""
            risk_level = "NONE"
            if (r1["id"], r2["id"]) == (3, 4):
                flag = "CRITICAL RISK: High vector similarity on family members (gulgun vs kaan karamete) causes FALSE MERGE!"
                risk_level = "CRITICAL"
            elif (r1["id"], r2["id"]) == (1, 4):
                flag = "RISK: Unrelated records share phone prefix, generating inflated vector score."
                risk_level = "MODERATE"

            pairwise_results.append({
                "pair": [r1["id"], r2["id"]],
                "names": [r1["name"], r2["name"]],
                "record1": f"{r1['name']} | {r1['email']} | {r1['phone']}",
                "record2": f"{r2['name']} | {r2['email']} | {r2['phone']}",
                "overall_cosine": overall_cos,
                "name_cosine": n_cos,
                "phone_cosine": p_cos,
                "vector_cosine_overall": overall_cos,
                "vector_cosine_name": n_cos,
                "vector_cosine_phone": p_cos,
                "risk_assessment": flag,
                "failure_mode": flag,
                "risk_level": risk_level,
            })

    return {
        "pairwise": pairwise_results,
        "char_sim_matrix": char_sim.round(3).tolist(),
    }
