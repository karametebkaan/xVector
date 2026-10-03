export interface RecordItem {
  id: number;
  name: string;
  email: string;
  phone: string;
}

export interface NormalizedRecord {
  id: number;
  name: string;
  email: string;
  phone: string;
  phone_7: string;
  phone_prefix_4: string;
  phone_suffix_4: string;
  email_user: string;
  email_user_prefix_4: string;
  first_token: string;
  last_token: string;
  first_initial: string;
}

export interface CandidatePair {
  id1: number;
  id2: number;
  rules: string;
}

export interface DimensionBreakdown {
  val1: string;
  val2: string;
  score: number;
  weight: number;
  weighted_contribution: number;
  primary_rule: string;
  all_reasons: string[];
  is_conflict?: boolean;
}

export interface CompositeBreakdown {
  name_component: number;
  email_component: number;
  phone_component: number;
  raw_sum: number;
  final_confidence: number;
  formula_string: string;
  penalty_applied: boolean;
  penalty_note: string;
}

export interface PairBreakdown {
  name: DimensionBreakdown;
  email: DimensionBreakdown;
  phone: DimensionBreakdown;
  composite: CompositeBreakdown;
}

export interface ScoredPair {
  id1: number;
  id2: number;
  name1: string;
  name2: string;
  email1?: string;
  email2?: string;
  phone1?: string;
  phone2?: string;
  name_sim: number;
  email_sim: number;
  phone_sim: number;
  composite_score: number;
  reasons: string[];
  is_match: boolean;
  conflict_flag: boolean;
  matched_rules?: string;
  breakdown?: PairBreakdown;
}

export interface GraphEdge {
  id1: number;
  id2: number;
  rel_type: string;
  weight: number;
  reasons: string;
}

export interface NodeCentrality {
  id: number;
  name: string;
  weighted_degree: number;
  composite_pagerank: number;
  name_pagerank: number;
  email_pagerank: number;
  phone_pagerank: number;
}

export interface GoldenEntity {
  cluster_id: number;
  member_ids: number[];
  centroid_id: number;
  centroid_name: string;
  canonical_name: string;
  name_source_id: number;
  aliases: string[];
  primary_email: string;
  email_source_id: number;
  all_emails: string[];
  primary_phone: string;
  phone_source_id: number;
  all_phones: string[];
  cluster_size: number;
  average_confidence: number;
  min_confidence: number;
}

export interface BenchmarkComparison {
  pair: [number, number];
  names: [string, string];
  overall_cosine: number;
  name_cosine: number;
  phone_cosine: number;
  failure_mode: string;
  risk_level: 'NONE' | 'MODERATE' | 'CRITICAL';
}

export interface PipelinePayload {
  records: RecordItem[];
  normalized: NormalizedRecord[];
  candidate_pairs: CandidatePair[];
  scored_candidates: ScoredPair[];
  all_pair_scores: ScoredPair[];
  edges: GraphEdge[];
  wcc_clusters: Record<string, number[]>;
  centrality: NodeCentrality[];
  attribute_pagerank: {
    NAME: Record<string, number>;
    EMAIL: Record<string, number>;
    PHONE: Record<string, number>;
  };
  golden_entities: GoldenEntity[];
  benchmark: BenchmarkComparison[];
  dot_heterogeneous: string;
  dot_multilayer: string;
}

export interface SystemStatus {
  status: string;
  falkordb_connected: boolean;
  duckdb_ready: boolean;
  graph_name: string;
  records_count: number;
}
