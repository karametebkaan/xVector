"""
Unit and integration tests for xMatch Multi-Layer Entity Resolution pipeline.
Tests blocking, similarity scoring, multi-layer FalkorDB GraphBLAS clustering,
combination queries, and multi-dimensional Golden Record synthesis.
Strictly Zero NetworkX.
"""

import pytest
from xmatch.similarity import (
    name_similarity,
    email_similarity,
    phone_similarity,
    compute_pair_similarity
)
from xmatch.blocking import DuckDBBlocker
from xmatch.graph_engine import FalkorIdentityGraph, DisjointSetUnion
from xmatch.golden_record import (
    GoldenRecordResolver,
    compute_name_quality,
    compute_email_quality,
    compute_phone_quality
)


SAMPLE_DATA = [
    {"id": 1, "name": "kaan", "email": "kpapaz@gmail", "phone": "2696227"},
    {"id": 2, "name": "kkaramete", "email": "kalles@gmail.com", "phone": "5182696226"},
    {"id": 3, "name": "kaan karamete", "email": "kallespapaz@gmail", "phone": "404356789"},
    {"id": 4, "name": "gulgun karamete", "email": "gkaramete@kmail.com", "phone": "2696777"},
]


def test_no_networkx_imported():
    """Verify that networkx is strictly NOT in sys.modules."""
    import sys
    assert "networkx" not in sys.modules, "Violation: networkx was imported!"


def test_token_containment_name():
    score, reasons, conflict = name_similarity("kaan", "kaan karamete")
    assert score > 0.85
    assert not conflict
    assert any("token_containment" in r for r in reasons)


def test_initial_surname_name():
    score, reasons, conflict = name_similarity("kkaramete", "kaan karamete")
    assert score >= 0.90
    assert not conflict
    assert any("initial_surname_match" in r for r in reasons)


def test_family_conflict_detection():
    score, reasons, conflict = name_similarity("gulgun karamete", "kaan karamete")
    assert conflict is True
    assert score <= 0.35
    assert any("family_surname_shared" in r for r in reasons)


def test_email_subword_containment():
    score1, reasons1 = email_similarity("kpapaz@gmail", "kallespapaz@gmail")
    assert score1 >= 0.75
    assert any("email" in r for r in reasons1)

    score2, reasons2 = email_similarity("kalles@gmail.com", "kallespapaz@gmail")
    assert score2 >= 0.85
    assert any("email_username_prefix" in r for r in reasons2)


def test_phone_suffix_distance():
    score, reasons = phone_similarity("2696227", "5182696226")
    assert score >= 0.80
    assert any("phone_suffix_1digit_diff" in r for r in reasons)


def test_duckdb_blocking():
    blocker = DuckDBBlocker()
    blocker.load_records(SAMPLE_DATA)
    candidates = blocker.generate_candidate_pairs()
    pairs = set((c[0], c[1]) for c in candidates)
    
    # Must capture bridge connections
    assert (1, 3) in pairs  # Shared first token 'kaan'
    assert (2, 3) in pairs  # Shared email prefix / initial surname


def test_disjoint_set_union():
    dsu = DisjointSetUnion([1, 2, 3, 4])
    dsu.union(1, 3)
    dsu.union(2, 3)
    clusters = dsu.get_clusters()
    
    found_k = False
    for root, members in clusters.items():
        if set(members) == {1, 2, 3}:
            found_k = True
    assert found_k is True
    assert [4] in clusters.values()


def test_falkordb_multi_layer_graphblas():
    falkor = FalkorIdentityGraph(graph_name="test_xmatch_multilayer")
    falkor.reset_graph()
    falkor.load_nodes(SAMPLE_DATA)

    all_scores = []
    for i in range(len(SAMPLE_DATA)):
        for j in range(i + 1, len(SAMPLE_DATA)):
            all_scores.append(compute_pair_similarity(SAMPLE_DATA[i], SAMPLE_DATA[j]))

    # Load multi-layer graph
    falkor.load_similarity_edges(all_scores, threshold=0.60, load_dimensional_layers=True)

    # 1. Dimensional PageRank checks
    name_pr = falkor.get_dimensional_pagerank("MATCHES_NAME")
    email_pr = falkor.get_dimensional_pagerank("MATCHES_EMAIL")
    phone_pr = falkor.get_dimensional_pagerank("MATCHES_PHONE")

    assert name_pr[3] > name_pr[1]  # Node 3 is name hub
    assert email_pr[3] > email_pr[1]  # Node 3 is email hub
    assert phone_pr[2] > phone_pr[3]  # Node 2 is phone hub (5182696226)

    # 2. Combination query (pairs matching on both Name and Email)
    combos = falkor.query_combination_matches("name", "email")
    combo_pairs = set((c["id1"], c["id2"]) for c in combos)
    assert (1, 3) in combo_pairs
    assert (2, 3) in combo_pairs

    # 3. Transitive multi-hop path
    paths = falkor.find_multi_hop_paths(1, 2)
    assert len(paths) >= 1

    # 4. Multi-dimensional attribute survivorship
    centrality = falkor.get_node_centrality()
    cent_map = {c["id"]: c for c in centrality}
    wcc = falkor.run_wcc()
    resolver = GoldenRecordResolver(SAMPLE_DATA, cent_map)
    edges = falkor.get_all_edges()

    # Cluster 0 must have Node 3 as centroid, Node 3 for name, Node 2 for phone
    cluster_0_id = [cid for cid, m in wcc.items() if 3 in m][0]
    golden = resolver.resolve_cluster(cluster_0_id, wcc[cluster_0_id], edges)
    
    assert golden["canonical_name"] == "kaan karamete"
    assert golden["name_source_id"] == 3
    assert golden["primary_email"] == "kallespapaz@gmail"
    assert golden["email_source_id"] == 3
    assert golden["primary_phone"] == "5182696226"
    assert golden["phone_source_id"] == 2
    assert golden["centroid_id"] == 3

    # Clean up
    falkor.reset_graph()


def test_heterogeneous_attribute_graph():
    """Test loading and running PageRank on :NAME, :EMAIL, :PHONE attribute nodes."""
    falkor = FalkorIdentityGraph(graph_name="test_xmatch_hetero")
    falkor.reset_graph()
    falkor.load_nodes(SAMPLE_DATA)

    all_scores = []
    for i in range(len(SAMPLE_DATA)):
        for j in range(i + 1, len(SAMPLE_DATA)):
            all_scores.append(compute_pair_similarity(SAMPLE_DATA[i], SAMPLE_DATA[j]))

    falkor.load_heterogeneous_graph(SAMPLE_DATA, all_scores)

    name_pr = falkor.run_attribute_pagerank("NAME")
    email_pr = falkor.run_attribute_pagerank("EMAIL")
    phone_pr = falkor.run_attribute_pagerank("PHONE")

    # Name PageRank winner must be 'kaan karamete'
    assert name_pr["kaan karamete"] > name_pr["kaan"]
    assert name_pr["kaan karamete"] > name_pr["kkaramete"]

    # Email PageRank winner must be 'kallespapaz@gmail'
    assert email_pr["kallespapaz@gmail"] > email_pr["kpapaz@gmail"]
    assert email_pr["kallespapaz@gmail"] > email_pr["kalles@gmail.com"]

    # Phone PageRank winner must be '5182696226'
    assert phone_pr["5182696226"] > phone_pr["2696227"]

    falkor.reset_graph()

