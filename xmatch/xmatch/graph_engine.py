"""
FalkorDB GraphBLAS Multi-Layer (Multiplex) Identity Graph Engine.
Performs transitive entity resolution, Weakly Connected Components (WCC),
dimensional PageRank, multi-layer Cypher queries, and attribute survivorship directly on FalkorDB.
STRICTLY ZERO NETWORKX.
"""

from typing import List, Dict, Any, Optional
from falkordb import FalkorDB


class DisjointSetUnion:
    """
    High-performance Disjoint-Set Union (Union-Find) with path compression
    and union by rank. Used as local fallback / validator without NetworkX.
    """

    def __init__(self, elements: List[int]):
        self.parent = {e: e for e in elements}
        self.rank = {e: 0 for e in elements}

    def find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: int, j: int):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            if self.rank[root_i] < self.rank[root_j]:
                self.parent[root_i] = root_j
            elif self.rank[root_i] > self.rank[root_j]:
                self.parent[root_j] = root_i
            else:
                self.parent[root_j] = root_i
                self.rank[root_i] += 1

    def get_clusters(self) -> Dict[int, List[int]]:
        clusters: Dict[int, List[int]] = {}
        for element in self.parent:
            root = self.find(element)
            clusters.setdefault(root, []).append(element)
        return clusters


class FalkorIdentityGraph:
    """
    FalkorDB GraphBLAS Multi-Layer Identity Engine.
    Manages typed dimensional layers (:MATCHES_NAME, :MATCHES_EMAIL, :MATCHES_PHONE)
    and composite (:SIMILAR_TO) identity edges backed by GraphBLAS sparse matrices.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, graph_name: str = "xmatch_identity_graph"):
        self.host = host
        self.port = port
        self.graph_name = graph_name
        self.client = FalkorDB(host=self.host, port=self.port)
        self.graph = self.client.select_graph(self.graph_name)

    def reset_graph(self):
        """Delete existing graph to start clean."""
        try:
            self.client.connection.delete(self.graph_name)
        except Exception:
            pass
        self.graph = self.client.select_graph(self.graph_name)

    def load_nodes(self, records: List[Dict[str, Any]]):
        """Create :Record nodes in FalkorDB."""
        for r in records:
            name = (r.get("name") or "").replace("'", "\\'")
            email = (r.get("email") or "").replace("'", "\\'")
            phone = (r.get("phone") or "").replace("'", "\\'")
            q = f"CREATE (:Record {{id: {r['id']}, name: '{name}', email: '{email}', phone: '{phone}'}})"
            self.graph.query(q)

    def load_similarity_edges(
        self,
        edges: List[Dict[str, Any]],
        threshold: float = 0.60,
        load_family_edges: bool = False,
        load_dimensional_layers: bool = True
    ):
        """
        Populate the Multi-Layer (Multiplex) graph:
        - Layer 1: :MATCHES_NAME edges
        - Layer 2: :MATCHES_EMAIL edges
        - Layer 3: :MATCHES_PHONE edges
        - Layer 4: :SIMILAR_TO composite identity edges
        """
        for edge in edges:
            weight = edge["composite_confidence"]
            id1 = edge["id1"]
            id2 = edge["id2"]
            is_family = edge.get("is_family_conflict", False)
            reasons_str = "; ".join(edge.get("match_reasons", [])).replace("'", "\\'")

            if is_family and load_family_edges:
                q = f"""
                MATCH (a:Record {{id: {id1}}}), (b:Record {{id: {id2}}})
                CREATE (a)-[:FAMILY_OF {{
                    weight: {weight},
                    name_score: {edge['name_score']},
                    reasons: '{reasons_str}'
                }}]->(b)
                """
                self.graph.query(q)

            elif not is_family:
                # 1. Dimensional Layers (Name, Email, Phone)
                if load_dimensional_layers:
                    if edge.get("name_score", 0.0) >= 0.70:
                        q_name = f"""
                        MATCH (a:Record {{id: {id1}}}), (b:Record {{id: {id2}}})
                        CREATE (a)-[:MATCHES_NAME {{weight: {edge['name_score']}}}]->(b)
                        """
                        self.graph.query(q_name)

                    if edge.get("email_score", 0.0) >= 0.70:
                        q_email = f"""
                        MATCH (a:Record {{id: {id1}}}), (b:Record {{id: {id2}}})
                        CREATE (a)-[:MATCHES_EMAIL {{weight: {edge['email_score']}}}]->(b)
                        """
                        self.graph.query(q_email)

                    if edge.get("phone_score", 0.0) >= 0.70:
                        q_phone = f"""
                        MATCH (a:Record {{id: {id1}}}), (b:Record {{id: {id2}}})
                        CREATE (a)-[:MATCHES_PHONE {{weight: {edge['phone_score']}}}]->(b)
                        """
                        self.graph.query(q_phone)

                # 2. Composite Layer (:SIMILAR_TO)
                if weight >= threshold:
                    matched_dims = []
                    if edge.get("name_score", 0.0) >= 0.70:
                        matched_dims.append("name")
                    if edge.get("email_score", 0.0) >= 0.70:
                        matched_dims.append("email")
                    if edge.get("phone_score", 0.0) >= 0.70:
                        matched_dims.append("phone")
                    dims_str = str(matched_dims).replace("'", '"')

                    q_comp = f"""
                    MATCH (a:Record {{id: {id1}}}), (b:Record {{id: {id2}}})
                    CREATE (a)-[:SIMILAR_TO {{
                        weight: {weight},
                        name_score: {edge['name_score']},
                        email_score: {edge['email_score']},
                        phone_score: {edge['phone_score']},
                        dims: '{dims_str}',
                        reasons: '{reasons_str}'
                    }}]->(b)
                    """
                    self.graph.query(q_comp)

    def run_wcc(self) -> Dict[int, List[int]]:
        """
        Execute GraphBLAS Weakly Connected Components (WCC) on identity clusters.
        Returns mapping from component_id to list of record IDs.
        """
        res = self.graph.query("CALL algo.wcc()")
        clusters: Dict[int, List[int]] = {}
        for row in res.result_set:
            node, comp_id = row
            if "id" in node.properties:
                rec_id = int(node.properties["id"])
                clusters.setdefault(comp_id, []).append(rec_id)
        
        for comp_id in clusters:
            clusters[comp_id].sort()
        return clusters

    def get_dimensional_pagerank(self, edge_type: str = "SIMILAR_TO") -> Dict[int, float]:
        """
        Execute GraphBLAS PageRank on a specific dimensional layer:
        - 'MATCHES_NAME'
        - 'MATCHES_EMAIL'
        - 'MATCHES_PHONE'
        - 'SIMILAR_TO'
        """
        pr_map: Dict[int, float] = {}
        try:
            res = self.graph.query(f"CALL algo.pageRank('Record', '{edge_type}')")
            for row in res.result_set:
                node, pr = row
                pr_map[int(node.properties["id"])] = round(float(pr), 4)
        except Exception:
            pass
        return pr_map

    def get_node_centrality(self) -> List[Dict[str, Any]]:
        """
        Compute Weighted Degree Centrality and PageRank across composite and dimensional layers.
        """
        # Composite Weighted Degree
        deg_query = """
        MATCH (n:Record)
        OPTIONAL MATCH (n)-[r:SIMILAR_TO]-(m:Record)
        RETURN n.id as id, n.name as name, count(m) as degree, coalesce(sum(r.weight), 0.0) as weighted_degree
        ORDER BY weighted_degree DESC, id ASC
        """
        deg_res = self.graph.query(deg_query)

        # Compute PageRank for each layer
        pr_comp = self.get_dimensional_pagerank("SIMILAR_TO")
        pr_name = self.get_dimensional_pagerank("MATCHES_NAME")
        pr_email = self.get_dimensional_pagerank("MATCHES_EMAIL")
        pr_phone = self.get_dimensional_pagerank("MATCHES_PHONE")

        results = []
        for row in deg_res.result_set:
            rec_id = int(row[0])
            name = str(row[1])
            degree = int(row[2])
            weighted_degree = round(float(row[3]), 3)
            results.append({
                "id": rec_id,
                "name": name,
                "degree": degree,
                "weighted_degree": weighted_degree,
                "pagerank": pr_comp.get(rec_id, 0.0),
                "name_pagerank": pr_name.get(rec_id, 0.0),
                "email_pagerank": pr_email.get(rec_id, 0.0),
                "phone_pagerank": pr_phone.get(rec_id, 0.0),
            })
        return results

    def find_multi_hop_paths(self, id1: int, id2: int) -> List[Dict[str, Any]]:
        """
        Find transitive paths between two records using Cypher multi-hop pattern.
        """
        q = f"""
        MATCH p = (a:Record {{id: {id1}}})-[:SIMILAR_TO*1..3]-(b:Record {{id: {id2}}})
        RETURN [n in nodes(p) | n.id] as path_ids,
               [n in nodes(p) | n.name] as path_names,
               length(p) as hops
        """
        res = self.graph.query(q)
        paths = []
        seen = set()
        for row in res.result_set:
            path_ids = tuple(row[0])
            if path_ids not in seen:
                seen.add(path_ids)
                paths.append({
                    "path_ids": list(row[0]),
                    "path_names": list(row[1]),
                    "hops": int(row[2]),
                })
        return paths

    def query_combination_matches(self, dim1: str, dim2: str) -> List[Dict[str, Any]]:
        """
        Query records matching on a combination of two dimensions (e.g. NAME and EMAIL).
        Uses inner Cypher pattern matching across multiple edge types.
        """
        edge1 = f"MATCHES_{dim1.upper()}"
        edge2 = f"MATCHES_{dim2.upper()}"
        q = f"""
        MATCH (a:Record)-[r1:{edge1}]-(b:Record)
        MATCH (a)-[r2:{edge2}]-(b)
        WHERE a.id < b.id
        RETURN a.id as id1, a.name as name1, b.id as id2, b.name as name2,
               r1.weight as score1, r2.weight as score2
        """
        res = self.graph.query(q)
        results = []
        for row in res.result_set:
            results.append({
                "id1": int(row[0]),
                "name1": str(row[1]),
                "id2": int(row[2]),
                "name2": str(row[3]),
                f"{dim1}_score": float(row[4]),
                f"{dim2}_score": float(row[5]),
            })
        return results

    def get_all_edges(self) -> List[Dict[str, Any]]:
        """Retrieve all edges across all layers with metadata."""
        q = """
        MATCH (a:Record)-[r]->(b:Record)
        RETURN a.id as id1, a.name as name1,
               type(r) as rel_type,
               b.id as id2, b.name as name2,
               coalesce(r.weight, 0.0) as weight,
               coalesce(r.reasons, '') as reasons
        ORDER BY rel_type, id1, id2
        """
        res = self.graph.query(q)
        edges = []
        for row in res.result_set:
            edges.append({
                "id1": int(row[0]),
                "name1": str(row[1]),
                "rel_type": str(row[2]),
                "id2": int(row[3]),
                "name2": str(row[4]),
                "weight": round(float(row[5]), 3),
                "reasons": str(row[6]),
            })
        return edges

    def load_heterogeneous_graph(self, records: List[Dict[str, Any]], scores: List[Dict[str, Any]]):
        """
        Populate the unified heterogeneous graph with explicit attribute nodes:
        (:Record), (:NAME), (:EMAIL), and (:PHONE), with structural edges
        (:HAS_NAME, :HAS_EMAIL, :HAS_PHONE) and similarity edges (:SIMILAR_TO).
        """
        for r in records:
            rid = r["id"]
            name = (r.get("name") or "").replace("'", "\\'")
            email = (r.get("email") or "").replace("'", "\\'")
            phone = (r.get("phone") or "").replace("'", "\\'")

            # Create attribute nodes if they don't exist and link to record
            if name:
                self.graph.query(f"MERGE (n:NAME {{val: '{name}'}})")
                self.graph.query(f"MATCH (r:Record {{id: {rid}}}), (n:NAME {{val: '{name}'}}) MERGE (r)-[:HAS_NAME]->(n)")
            if email:
                self.graph.query(f"MERGE (e:EMAIL {{val: '{email}'}})")
                self.graph.query(f"MATCH (r:Record {{id: {rid}}}), (e:EMAIL {{val: '{email}'}}) MERGE (r)-[:HAS_EMAIL]->(e)")
            if phone:
                self.graph.query(f"MERGE (p:PHONE {{val: '{phone}'}})")
                self.graph.query(f"MATCH (r:Record {{id: {rid}}}), (p:PHONE {{val: '{phone}'}}) MERGE (r)-[:HAS_PHONE]->(p)")

        # Create similarity edges between attribute nodes
        records_by_id = {r["id"]: r for r in records}
        for s in scores:
            if s.get("conflict"):
                continue
            r1 = records_by_id.get(s["id1"])
            r2 = records_by_id.get(s["id2"])
            if not r1 or not r2:
                continue

            # Name similarity
            if s.get("name_score", 0.0) >= 0.70:
                n1 = r1["name"].replace("'", "\\'")
                n2 = r2["name"].replace("'", "\\'")
                w = s["name_score"]
                self.graph.query(
                    f"MATCH (a:NAME {{val: '{n1}'}}), (b:NAME {{val: '{n2}'}}) "
                    f"MERGE (a)-[:SIMILAR_TO {{weight: {w}}}]->(b)"
                )
            # Email similarity
            if s.get("email_score", 0.0) >= 0.70:
                e1 = r1["email"].replace("'", "\\'")
                e2 = r2["email"].replace("'", "\\'")
                w = s["email_score"]
                self.graph.query(
                    f"MATCH (a:EMAIL {{val: '{e1}'}}), (b:EMAIL {{val: '{e2}'}}) "
                    f"MERGE (a)-[:SIMILAR_TO {{weight: {w}}}]->(b)"
                )
            # Phone similarity
            if s.get("phone_score", 0.0) >= 0.70:
                p1 = r1["phone"].replace("'", "\\'")
                p2 = r2["phone"].replace("'", "\\'")
                w = s["phone_score"]
                self.graph.query(
                    f"MATCH (a:PHONE {{val: '{p1}'}}), (b:PHONE {{val: '{p2}'}}) "
                    f"MERGE (a)-[:SIMILAR_TO {{weight: {w}}}]->(b)"
                )

    def run_attribute_pagerank(self, label: str) -> Dict[str, float]:
        """
        Run GraphBLAS PageRank directly on attribute nodes of label (:NAME, :EMAIL, :PHONE).
        """
        pr_map = {}
        try:
            q = f"CALL algo.pageRank('{label}', 'SIMILAR_TO') YIELD node, score RETURN node.val, score"
            res = self.graph.query(q)
            for row in res.result_set:
                pr_map[str(row[0])] = round(float(row[1]), 4)
        except Exception:
            pass
        return pr_map

