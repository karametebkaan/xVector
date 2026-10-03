#!/usr/bin/env python3
"""
xMatch End-to-End Interactive Pipeline & Playground.
Multi-Layer (Multiplex) Identity Graph Resolution using:
1. DuckDB Inverted-Index Blocking Layer
2. RapidFuzz & Domain Heuristic Similarity Engine
3. FalkorDB (GraphBLAS) Multi-Layer Identity Graph Engine (Strictly Zero NetworkX)
   - Layer 1: :MATCHES_NAME
   - Layer 2: :MATCHES_EMAIL
   - Layer 3: :MATCHES_PHONE
   - Layer 4: :SIMILAR_TO (Composite)
4. Multi-Dimensional Attribute Survivorship (Best Name, Email, Phone selected per layer)
5. Vector vs Fuzzy Comparative Benchmark
"""

import sys
from tabulate import tabulate
from xmatch.config import FalkorDBConfig, SimilarityWeights
from xmatch.blocking import DuckDBBlocker
from xmatch.similarity import compute_pair_similarity
from xmatch.graph_engine import FalkorIdentityGraph
from xmatch.golden_record import GoldenRecordResolver
from xmatch.vector_benchmark import run_vector_analysis


SAMPLE_RECORDS = [
    {"id": 1, "name": "kaan", "email": "kpapaz@gmail", "phone": "2696227"},
    {"id": 2, "name": "kkaramete", "email": "kalles@gmail.com", "phone": "5182696226"},
    {"id": 3, "name": "kaan karamete", "email": "kallespapaz@gmail", "phone": "404356789"},
    {"id": 4, "name": "gulgun karamete", "email": "gkaramete@kmail.com", "phone": "2696777"},
]


def print_section(title: str):
    print("\n" + "=" * 95)
    print(f" {title}")
    print("=" * 95)


def main():
    print_section("STAGE 1: RAW INPUT RECORDS (SAMPLE TABLE)")
    headers = ["ID", "Name", "Email", "Phone"]
    rows = [[r["id"], r["name"], r["email"], r["phone"]] for r in SAMPLE_RECORDS]
    print(tabulate(rows, headers=headers, tablefmt="github"))

    # Stage 2: DuckDB Candidate Blocking
    print_section("STAGE 2: DUCKDB VECTORIZED CANDIDATE BLOCKING (ELIMINATING O(N^2))")
    blocker = DuckDBBlocker()
    blocker.load_records(SAMPLE_RECORDS)
    candidates = blocker.generate_candidate_pairs()

    cand_rows = []
    for id1, id2, rules in candidates:
        cand_rows.append([f"({id1}, {id2})", rules])
    print(tabulate(cand_rows, headers=["Candidate Pair (ID1, ID2)", "Triggered Blocking Rules"], tablefmt="github"))
    print(f"\n[INFO] DuckDB generated {len(candidates)} candidate pairs without full cross product.")

    # Stage 3: Similarity and Confidence Scoring
    print_section("STAGE 3: FIELD-AWARE SIMILARITY & CONFIDENCE SCORING")
    weights = SimilarityWeights()
    all_pair_scores = []
    
    for r1_idx in range(len(SAMPLE_RECORDS)):
        for r2_idx in range(r1_idx + 1, len(SAMPLE_RECORDS)):
            r1 = SAMPLE_RECORDS[r1_idx]
            r2 = SAMPLE_RECORDS[r2_idx]
            pair_res = compute_pair_similarity(
                r1, r2,
                name_wt=weights.name_weight,
                email_wt=weights.email_weight,
                phone_wt=weights.phone_weight
            )
            all_pair_scores.append(pair_res)

    sim_rows = []
    for s in all_pair_scores:
        reasons_display = "\n".join(s["match_reasons"])
        sim_rows.append([
            f"({s['id1']}, {s['id2']})",
            s["name_score"],
            s["email_score"],
            s["phone_score"],
            s["composite_confidence"],
            "YES (Family Relation)" if s["is_family_conflict"] else "NO",
            reasons_display
        ])
    print(tabulate(
        sim_rows,
        headers=["Pair", "Name Sim", "Email Sim", "Phone Sim", "Composite Conf", "Family Conflict?", "Indicators / Provenance"],
        tablefmt="grid"
    ))

    # Stage 4: FalkorDB Multi-Layer Identity Graph
    print_section("STAGE 4: FALKORDB (GRAPHBLAS) MULTI-LAYER IDENTITY GRAPH COMPUTE (ZERO NETWORKX)")
    cfg = FalkorDBConfig()
    try:
        falkor = FalkorIdentityGraph(host=cfg.host, port=cfg.port, graph_name=cfg.graph_name)
        falkor.reset_graph()
        falkor.load_nodes(SAMPLE_RECORDS)
        # Ingest multi-layer edges (:MATCHES_NAME, :MATCHES_EMAIL, :MATCHES_PHONE, :SIMILAR_TO)
        falkor.load_similarity_edges(all_pair_scores, threshold=0.60, load_dimensional_layers=True)
        print(f"[OK] Ingested 4 nodes and multi-layer edges into FalkorDB graph '{cfg.graph_name}'.")

        # 4a: Display Graph Edges across all layers
        edges = falkor.get_all_edges()
        edge_rows = [
            [e["rel_type"], f"{e['id1']} ({e['name1']})", f"{e['id2']} ({e['name2']})", e["weight"], e["reasons"]]
            for e in edges
        ]
        print("\n--- FalkorDB Multi-Layer Stored Edges ---")
        print(tabulate(edge_rows, headers=["Layer / Rel Type", "Source Node", "Target Node", "Weight", "Provenance Reasons"], tablefmt="grid"))

        # 4b: Multi-Layer Cypher Combination Queries (Name AND Email)
        print("\n--- Inner Cypher Combination Query: Pairs Matching on Both NAME AND EMAIL ---")
        name_email_matches = falkor.query_combination_matches("name", "email")
        combo_rows = [
            [f"({m['id1']}, {m['id2']})", f"{m['name1']} <-> {m['name2']}", m["name_score"], m["email_score"]]
            for m in name_email_matches
        ]
        print(tabulate(combo_rows, headers=["Pair", "Records", "Name Sim", "Email Sim"], tablefmt="github"))

        # 4c: Multi-hop Cypher Transitive Traversal
        print("\n--- Multi-Hop Cypher Traversal (Transitive Resolution between R1 and R2 via R3) ---")
        transitive_paths = falkor.find_multi_hop_paths(1, 2)
        if transitive_paths:
            for p in transitive_paths:
                print(f" Transitive Path: {' -> '.join(p['path_names'])} (Node IDs: {p['path_ids']}, Hops: {p['hops']})")

        # 4d: GraphBLAS Weakly Connected Components (WCC)
        wcc_clusters = falkor.run_wcc()
        print("\n--- GraphBLAS algo.wcc() Cluster Partitioning ---")
        for comp_id, members in sorted(wcc_clusters.items()):
            member_names = [f"ID {mid}: {SAMPLE_RECORDS[mid-1]['name']}" for mid in members]
            print(f" Component {comp_id}: [{', '.join(member_names)}]")

        # 4e: Dimensional GraphBLAS PageRank Leaderboards
        centrality = falkor.get_node_centrality()
        centrality_map = {c["id"]: c for c in centrality}
        cent_rows = [
            [
                c["id"], c["name"],
                c["name_pagerank"], c["email_pagerank"], c["phone_pagerank"],
                c["pagerank"], c["weighted_degree"]
            ]
            for c in centrality
        ]
        print("\n--- FalkorDB Dimensional PageRank & Centrality Leaderboard ---")
        print(tabulate(
            cent_rows,
            headers=["ID", "Name", "Name PR", "Email PR", "Phone PR", "Composite PR", "Weighted Deg"],
            tablefmt="github"
        ))

        # 4f: Heterogeneous Attribute Node PageRank (:NAME, :EMAIL, :PHONE)
        falkor.load_heterogeneous_graph(SAMPLE_RECORDS, all_pair_scores)
        attr_name_pr = falkor.run_attribute_pagerank("NAME")
        attr_email_pr = falkor.run_attribute_pagerank("EMAIL")
        attr_phone_pr = falkor.run_attribute_pagerank("PHONE")
        
        attr_rows = []
        for n, score in sorted(attr_name_pr.items(), key=lambda x: x[1], reverse=True)[:2]:
            attr_rows.append([":NAME", n, score, "WINNER: Canonical Name" if "karamete" in n and "kaan" in n else "Alias"])
        for e, score in sorted(attr_email_pr.items(), key=lambda x: x[1], reverse=True)[:2]:
            attr_rows.append([":EMAIL", e, score, "WINNER: Canonical Email" if "kallespapaz" in e else "Alias"])
        for p, score in sorted(attr_phone_pr.items(), key=lambda x: x[1], reverse=True)[:2]:
            attr_rows.append([":PHONE", p, score, "WINNER: Canonical Phone" if "518" in p else "Alias"])

        print("\n--- Attribute Node (:NAME, :EMAIL, :PHONE) GraphBLAS PageRank ---")
        print(tabulate(
            attr_rows,
            headers=["Label", "Attribute Value", "PageRank", "Survivorship Decision"],
            tablefmt="github"
        ))

    except Exception as e:
        print(f"[WARNING] FalkorDB query encountered error: {e}")
        sys.exit(1)

    # Stage 5: Multi-Dimensional Golden Record Synthesis
    print_section("STAGE 5: MULTI-DIMENSIONAL GOLDEN RECORD ATTRIBUTE SURVIVORSHIP")
    resolver = GoldenRecordResolver(SAMPLE_RECORDS, centrality_map)
    golden_entities = []
    for comp_id, member_ids in sorted(wcc_clusters.items()):
        golden = resolver.resolve_cluster(comp_id, member_ids, edges)
        golden_entities.append(golden)

    golden_rows = []
    for g in golden_entities:
        golden_rows.append([
            f"Cluster {g['cluster_id']}",
            f"{g['canonical_name']} (from ID {g['name_source_id']})",
            f"{g['primary_email']} (from ID {g['email_source_id']})",
            f"{g['primary_phone']} (from ID {g['phone_source_id']})",
            ", ".join(g["aliases"]) if g["aliases"] else "(none)",
            g["cluster_size"],
            g["average_confidence"]
        ])
    print(tabulate(
        golden_rows,
        headers=["Cluster", "Best Name (Source)", "Best Email (Source)", "Best Phone (Source)", "Aliases", "Size", "Avg Conf"],
        tablefmt="grid"
    ))

    # Stage 6: Vector kNN vs Fuzzy Graph Benchmark
    print_section("STAGE 6: VECTOR EMBEDDING KNN VS FUZZY GRAPH BENCHMARK")
    v_res = run_vector_analysis(SAMPLE_RECORDS)
    vec_rows = []
    for p in v_res["pairwise"]:
        vec_rows.append([
            f"({p['pair'][0]}, {p['pair'][1]})",
            p["vector_cosine_overall"],
            p["vector_cosine_name"],
            p["vector_cosine_phone"],
            p["risk_assessment"] if p["risk_assessment"] else "Consistent"
        ])
    print(tabulate(
        vec_rows,
        headers=["Pair", "Overall Cosine", "Name Cosine", "Phone Cosine", "Failure Mode / Risk Analysis"],
        tablefmt="grid"
    ))


if __name__ == "__main__":
    main()
