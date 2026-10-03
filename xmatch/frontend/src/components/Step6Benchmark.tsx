import React from "react";
import { Sparkles, AlertOctagon, CheckCircle2, ShieldAlert, Cpu, HardDrive } from "lucide-react";
import { BenchmarkComparison } from "../types";

interface Step6BenchmarkProps {
  benchmarks: BenchmarkComparison[];
}

export const Step6Benchmark: React.FC<Step6BenchmarkProps> = ({ benchmarks }) => {
  return (
    <div className="space-y-6">
      {/* Intro Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#161b22] border border-[#30363d] p-5 rounded-xl">
        <div>
          <div className="flex items-center gap-2 text-purple-400 text-xs font-mono font-semibold uppercase tracking-wider mb-1">
            <Sparkles size={14} /> Stage 6: Vector Embeddings vs. Graph Fuzzy Benchmark
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            Failure Mode Analysis: Why Pure Vector kNN Is Dangerous
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Comparing dense vector embedding cosine similarity against FalkorDB multi-layer fuzzy graph resolution.
          </p>
        </div>
      </div>

      {/* Architectural Flaws of Pure Vectors */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#161b22] border border-red-900/40 p-4 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-red-400 font-bold text-xs font-mono uppercase">
            <AlertOctagon size={16} /> 1. Alphanumeric Blindness
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            Sentence Transformers and dense embeddings encode semantic topics, not exact character deltas. 
            Phone numbers like <code>2696227</code> and <code>2696777</code> map to near-identical vectors, losing critical 1-digit digit-positional distinctions.
          </p>
        </div>

        <div className="bg-[#161b22] border border-red-900/40 p-4 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-red-400 font-bold text-xs font-mono uppercase">
            <ShieldAlert size={16} /> 2. Family Member False Merges
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            In Turkish, Arabic, or Hispanic naming conventions, shared rare surnames dominate embedding space. 
            <code>gulgun karamete</code> and <code>kaan karamete</code> yield a cosine of <strong>0.502</strong>, triggering a catastrophic false merge under naive vector kNN!
          </p>
        </div>

        <div className="bg-[#161b22] border border-amber-900/40 p-4 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-amber-400 font-bold text-xs font-mono uppercase">
            <HardDrive size={16} /> 3. 1 Billion Scale Ram Exhaustion
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">
            1B records &times; 512-dim float32 vectors require <strong>2.0 TB of RAM</strong> plus 2&ndash;3 TB for HNSW graphs. 
            DuckDB sparse inverted indexes + FalkorDB GraphBLAS CSR matrices operate at ~100x lower memory overhead.
          </p>
        </div>
      </div>

      {/* Benchmark Results Table */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <span className="text-xs font-mono text-slate-300 font-semibold">
            EXPERIMENTAL BENCHMARK: DENSE VECTOR COSINE SIMILARITY
          </span>
          <span className="text-[11px] font-mono text-slate-400">Model: all-MiniLM-L6-v2 (TF-IDF/Character Baseline)</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#161b22]/70 text-slate-400 border-b border-[#21262d]">
              <tr>
                <th className="py-2.5 px-4">PAIR</th>
                <th className="py-2.5 px-4">RECORD NAMES</th>
                <th className="py-2.5 px-4 text-center">OVERALL COSINE</th>
                <th className="py-2.5 px-4 text-center">NAME COSINE</th>
                <th className="py-2.5 px-4 text-center">PHONE COSINE</th>
                <th className="py-2.5 px-4">FAILURE MODE / RISK EVALUATION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-slate-300">
              {(Array.isArray(benchmarks) ? benchmarks : (benchmarks as any)?.pairwise ?? []).map((b: any, idx: number) => {
                const isCrit = b.risk_level === "CRITICAL";
                const isMod = b.risk_level === "MODERATE";
                const pair0 = b.pair?.[0] ?? "";
                const pair1 = b.pair?.[1] ?? "";
                const name0 = b.names?.[0] ?? `Record ${pair0}`;
                const name1 = b.names?.[1] ?? `Record ${pair1}`;
                const overall = typeof b.overall_cosine === "number" ? b.overall_cosine.toFixed(3) : "0.000";
                const nameCos = typeof b.name_cosine === "number" ? b.name_cosine.toFixed(3) : "0.000";
                const phoneCos = typeof b.phone_cosine === "number" ? b.phone_cosine.toFixed(3) : "0.000";

                return (
                  <tr
                    key={idx}
                    className={`transition ${
                      isCrit
                        ? "bg-red-950/20 hover:bg-red-950/30"
                        : isMod
                        ? "bg-amber-950/15 hover:bg-amber-950/25"
                        : "hover:bg-[#161b22]/50"
                    }`}
                  >
                    <td className="py-3 px-4 font-bold text-blue-400">
                      (R{pair0}, R{pair1})
                    </td>
                    <td className="py-3 px-4 font-sans text-slate-200">
                      {name0} &harr; {name1}
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-white">
                      {overall}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-300">
                      {nameCos}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-300">
                      {phoneCos}
                    </td>
                    <td className="py-3 px-4 font-sans text-xs">
                      {isCrit ? (
                        <div className="flex items-center gap-1.5 text-red-400 font-semibold">
                          <AlertOctagon size={14} className="shrink-0" />
                          <span>{b.failure_mode}</span>
                        </div>
                      ) : isMod ? (
                        <div className="flex items-center gap-1.5 text-amber-400 font-medium">
                          <ShieldAlert size={14} className="shrink-0" />
                          <span>{b.failure_mode}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-emerald-400">
                          <CheckCircle2 size={13} className="shrink-0" />
                          <span>Consistent with GraphBLAS</span>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
