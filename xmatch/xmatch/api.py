"""
FastAPI Backend API for xMatch Identity Resolution & Golden Entity Synthesis.
Exposes endpoints for React UI to interact with DuckDB blocking and FalkorDB GraphBLAS engine.
"""

import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from xmatch.config import FalkorDBConfig, SAMPLE_RECORDS
from xmatch.blocking import DuckDBBlocker, create_blocking_keys
from xmatch.similarity import compute_pair_similarity
from xmatch.graph_engine import FalkorIdentityGraph
from xmatch.golden_record import GoldenRecordResolver
from xmatch.vector_benchmark import run_vector_analysis

app = FastAPI(
    title="xMatch Identity Resolution API",
    description="Backend API for xMatch Entity Resolution, FalkorDB GraphBLAS Engine & Graphviz DOT Visualizer",
    version="0.1.0"
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cfg = FalkorDBConfig()


def get_dot_heterogeneous() -> str:
    """Read the standalone Graphviz DOT definition for the heterogeneous graph."""
    dot_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "identity_graph.dot")
    if os.path.exists(dot_file):
        with open(dot_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def get_dot_multilayer(records: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> str:
    """Generate Graphviz DOT for the multi-layer record graph."""
    lines = [
        "digraph MultiLayerRecordGraph {",
        '    graph [rankdir=LR, bgcolor="#0d1117", fontname="Helvetica", pad="0.5", nodesep="0.7", ranksep="1.0"];',
        '    node [fontname="Helvetica", fontsize=11, style="filled,rounded", shape=box, margin="0.2,0.15"];',
        '    edge [fontname="Helvetica", fontsize=9];',
        ""
    ]
    for r in records:
        rid = r["id"]
        is_centroid = rid == 3
        fill = "#1c3a5e" if is_centroid else ("#21262d" if rid == 4 else "#161b22")
        stroke = "#58a6ff" if is_centroid else ("#f85149" if rid == 4 else "#388bfd")
        font = "#79c0ff" if is_centroid else ("#ff7b72" if rid == 4 else "#e6edf3")
        pen = ' penwidth=2.5,' if is_centroid else ''
        lines.append(f'    r{rid} [label="Record {rid}\\n{r["name"]}\\n{r["email"]}\\n{r["phone"]}", fillcolor="{fill}", color="{stroke}", fontcolor="{font}",{pen}];')

    lines.append("")
    for e in edges:
        id1, id2 = e["id1"], e["id2"]
        rtype = e.get("rel_type", "SIMILAR_TO")
        w = e.get("weight", 0.0)
        reasons = e.get("reasons", "")
        if rtype == "SIMILAR_TO":
            lines.append(f'    r{id1} -> r{id2} [label="CONFIDENCE: {w}", color="#58a6ff", penwidth=2.5, fontcolor="#79c0ff", dir=both];')
        elif rtype == "MATCHES_NAME":
            lines.append(f'    r{id1} -> r{id2} [label="NAME: {w}", color="#3fb950", penwidth=1.5, fontcolor="#7ee787", style=dashed, dir=both];')
        elif rtype == "MATCHES_EMAIL":
            lines.append(f'    r{id1} -> r{id2} [label="EMAIL: {w}", color="#d29922", penwidth=1.5, fontcolor="#f0883e", style=dashed, dir=both];')
        elif rtype == "MATCHES_PHONE":
            lines.append(f'    r{id1} -> r{id2} [label="PHONE: {w}", color="#a371f7", penwidth=1.5, fontcolor="#d2a8ff", style=dashed, dir=both];')

    lines.append("}")
    return "\n".join(lines)


def execute_pipeline(records: List[Dict[str, Any]], threshold: float = 0.60) -> Dict[str, Any]:
    """Execute the full end-to-end pipeline and return structured results."""
    # 1. DuckDB Ingestion & Blocking
    duck = DuckDBBlocker()
    duck.load_records(records)
    normalized = [create_blocking_keys(r) for r in records]
    raw_candidates = duck.generate_candidate_pairs()
    candidate_pairs = [{"id1": c[0], "id2": c[1], "rules": c[2]} for c in raw_candidates]

    rec_map = {r["id"]: r for r in records}

    # 2. Field-aware Similarity Scoring
    scored_candidates = []
    for c in candidate_pairs:
        id1, id2 = c["id1"], c["id2"]
        r1 = rec_map[id1]
        r2 = rec_map[id2]
        score_res = compute_pair_similarity(r1, r2)
        score_res["matched_rules"] = c["rules"]
        score_res["name1"] = r1.get("name", f"Record {id1}")
        score_res["name2"] = r2.get("name", f"Record {id2}")
        score_res["email1"] = r1.get("email", "")
        score_res["email2"] = r2.get("email", "")
        score_res["phone1"] = r1.get("phone", "")
        score_res["phone2"] = r2.get("phone", "")
        score_res["name_sim"] = score_res["name_score"]
        score_res["email_sim"] = score_res["email_score"]
        score_res["phone_sim"] = score_res["phone_score"]
        score_res["composite_score"] = score_res["composite_confidence"]
        score_res["conflict_flag"] = score_res["is_family_conflict"]
        score_res["reasons"] = score_res["match_reasons"]
        score_res["is_match"] = score_res["composite_confidence"] >= threshold and not score_res["is_family_conflict"]
        scored_candidates.append(score_res)

    # 3. All pairs for complete matrix
    all_pairs = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            r1 = records[i]
            r2 = records[j]
            pair_sim = compute_pair_similarity(r1, r2)
            pair_sim["name1"] = r1.get("name", f"Record {r1['id']}")
            pair_sim["name2"] = r2.get("name", f"Record {r2['id']}")
            pair_sim["email1"] = r1.get("email", "")
            pair_sim["email2"] = r2.get("email", "")
            pair_sim["phone1"] = r1.get("phone", "")
            pair_sim["phone2"] = r2.get("phone", "")
            pair_sim["name_sim"] = pair_sim["name_score"]
            pair_sim["email_sim"] = pair_sim["email_score"]
            pair_sim["phone_sim"] = pair_sim["phone_score"]
            pair_sim["composite_score"] = pair_sim["composite_confidence"]
            pair_sim["conflict_flag"] = pair_sim["is_family_conflict"]
            pair_sim["reasons"] = pair_sim["match_reasons"]
            pair_sim["is_match"] = pair_sim["composite_confidence"] >= threshold and not pair_sim["is_family_conflict"]
            all_pairs.append(pair_sim)

    # 4. FalkorDB GraphBLAS Ingest
    falkor = FalkorIdentityGraph(host=cfg.host, port=cfg.port, graph_name=cfg.graph_name)
    falkor.reset_graph()
    falkor.load_nodes(records)
    falkor.load_similarity_edges(all_pairs, threshold=threshold, load_dimensional_layers=True)
    falkor.load_heterogeneous_graph(records, all_pairs)

    edges = falkor.get_all_edges()
    wcc = falkor.run_wcc()
    centrality = falkor.get_node_centrality()
    for c in centrality:
        c["composite_pagerank"] = c.get("pagerank", 0.0)
    centrality_map = {c["id"]: c for c in centrality}

    attr_name_pr = falkor.run_attribute_pagerank("NAME")
    attr_email_pr = falkor.run_attribute_pagerank("EMAIL")
    attr_phone_pr = falkor.run_attribute_pagerank("PHONE")

    # 5. Golden Record Survivorship
    resolver = GoldenRecordResolver(records, centrality_map)
    golden_entities = []
    for comp_id, member_ids in sorted(wcc.items()):
        golden = resolver.resolve_cluster(comp_id, member_ids, edges)
        golden_entities.append(golden)

    # 6. Vector Benchmark
    benchmarks_raw = run_vector_analysis(records)
    benchmark_list = (
        benchmarks_raw.get("pairwise", [])
        if isinstance(benchmarks_raw, dict)
        else benchmarks_raw
    )

    # DOT definitions
    dot_hetero = get_dot_heterogeneous()
    dot_multi = get_dot_multilayer(records, edges)

    return {
        "records": records,
        "normalized": normalized,
        "candidate_pairs": candidate_pairs,
        "scored_candidates": scored_candidates,
        "all_pair_scores": all_pairs,
        "edges": edges,
        "wcc_clusters": {str(k): v for k, v in wcc.items()},
        "centrality": centrality,
        "attribute_pagerank": {
            "NAME": attr_name_pr,
            "EMAIL": attr_email_pr,
            "PHONE": attr_phone_pr
        },
        "golden_entities": golden_entities,
        "benchmark": benchmark_list,
        "dot_heterogeneous": dot_hetero,
        "dot_multilayer": dot_multi
    }


class RunRequest(BaseModel):
    threshold: float = 0.60
    records: Optional[List[Dict[str, Any]]] = None


class CypherRequest(BaseModel):
    query: str


@app.get("/api/status")
def get_status():
    """Health check and engine verification."""
    falkor_ok = False
    try:
        falkor = FalkorIdentityGraph(host=cfg.host, port=cfg.port, graph_name=cfg.graph_name)
        res = falkor.graph.query("RETURN 1")
        falkor_ok = len(res.result_set) > 0
    except Exception:
        pass

    return {
        "status": "healthy",
        "falkordb_connected": falkor_ok,
        "duckdb_ready": True,
        "networkx_used": False,
        "graph_name": cfg.graph_name,
        "records_count": len(SAMPLE_RECORDS)
    }


@app.get("/api/pipeline")
def get_pipeline_data(threshold: float = 0.60):
    """Retrieve full pipeline data computed with default or specified threshold."""
    try:
        return execute_pipeline(SAMPLE_RECORDS, threshold=threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/run")
def run_pipeline(req: RunRequest):
    """Re-run pipeline with custom threshold or custom records."""
    records = req.records or SAMPLE_RECORDS
    try:
        return execute_pipeline(records, threshold=req.threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cypher")
def run_cypher_query(req: CypherRequest):
    """Execute raw openCypher query directly against FalkorDB."""
    try:
        falkor = FalkorIdentityGraph(host=cfg.host, port=cfg.port, graph_name=cfg.graph_name)
        res = falkor.graph.query(req.query)
        headers = res.header if hasattr(res, "header") else []
        column_names = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in headers]
        rows = []
        for r in res.result_set:
            row_vals = []
            for item in r:
                if hasattr(item, "properties"):
                    row_vals.append(item.properties)
                elif hasattr(item, "id"):
                    row_vals.append(str(item))
                else:
                    row_vals.append(item)
            rows.append(row_vals)
        return {
            "query": req.query,
            "columns": column_names,
            "rows": rows,
            "row_count": len(rows)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cypher error: {str(e)}")


@app.get("/api/paths")
def get_transitive_paths(id1: int = 1, id2: int = 2):
    """Trace multi-hop paths between two record IDs."""
    try:
        falkor = FalkorIdentityGraph(host=cfg.host, port=cfg.port, graph_name=cfg.graph_name)
        paths = falkor.find_multi_hop_paths(id1, id2)
        return {"id1": id1, "id2": id2, "paths": paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
