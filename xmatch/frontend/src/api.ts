import { PipelinePayload, SystemStatus } from "./types";

const API_BASE = "/api";

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/status`);
  if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchPipelineData(threshold: number = 0.60): Promise<PipelinePayload> {
  const res = await fetch(`${API_BASE}/pipeline?threshold=${threshold}`);
  if (!res.ok) throw new Error(`Pipeline fetch failed: ${res.statusText}`);
  return res.json();
}

export async function runPipelineWithParams(threshold: number, records?: any[]): Promise<PipelinePayload> {
  const res = await fetch(`${API_BASE}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold, records }),
  });
  if (!res.ok) throw new Error(`Pipeline run failed: ${res.statusText}`);
  return res.json();
}

export async function executeCypher(query: string): Promise<{
  query: string;
  columns: string[];
  rows: any[][];
  row_count: number;
}> {
  const res = await fetch(`${API_BASE}/cypher`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Cypher query failed");
  }
  return res.json();
}

export async function fetchTransitivePaths(id1: number, id2: number): Promise<{
  id1: number;
  id2: number;
  paths: any[];
}> {
  const res = await fetch(`${API_BASE}/paths?id1=${id1}&id2=${id2}`);
  if (!res.ok) throw new Error(`Path query failed: ${res.statusText}`);
  return res.json();
}
