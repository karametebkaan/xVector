import React from "react";
import { Award, UserCheck, ShieldCheck, Mail, Phone, Users, CheckCircle2 } from "lucide-react";
import { GoldenEntity, NodeCentrality } from "../types";

interface Step5GoldenMasterProps {
  goldenEntities: GoldenEntity[];
  centrality: NodeCentrality[];
}

export const Step5GoldenMaster: React.FC<Step5GoldenMasterProps> = ({
  goldenEntities,
  centrality,
}) => {
  return (
    <div className="space-y-6">
      {/* Intro Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#161b22] border border-[#30363d] p-5 rounded-xl">
        <div>
          <div className="flex items-center gap-2 text-amber-400 text-xs font-mono font-semibold uppercase tracking-wider mb-1">
            <Award size={14} /> Stage 5: Multi-Dimensional Attribute Survivorship
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">Synthesized Master Golden Entities</h2>
          <p className="text-xs text-slate-400 mt-1">
            Best attributes selected across disparate touchpoints using dimensional GraphBLAS PageRank and completeness heuristics.
          </p>
        </div>
        <div className="text-xs font-mono bg-[#0d1117] border border-[#30363d] px-3.5 py-2 rounded-lg text-slate-300">
          Resolved Clusters: <span className="text-emerald-400 font-bold">{goldenEntities.length}</span>
        </div>
      </div>

      {/* Golden Entity Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {goldenEntities.map((g) => {
          const isMaster = g.cluster_size > 1;
          return (
            <div
              key={g.cluster_id}
              className={`rounded-2xl border p-6 flex flex-col justify-between transition shadow-xl ${
                isMaster
                  ? "bg-gradient-to-br from-[#0d1929] via-[#0d1117] to-[#121926] border-blue-500/50 shadow-blue-900/10"
                  : "bg-[#0d1117] border-[#21262d] shadow-black/40"
              }`}
            >
              <div>
                {/* Card Header */}
                <div className="flex items-center justify-between pb-4 border-b border-[#21262d]">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center font-bold ${
                        isMaster
                          ? "bg-blue-600 text-white shadow-md shadow-blue-500/30"
                          : "bg-[#21262d] text-slate-400"
                      }`}
                    >
                      {isMaster ? <Award size={20} /> : <UserCheck size={18} />}
                    </div>
                    <div>
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                        {isMaster ? "MASTER RESOLVED IDENTITY" : "ISOLATED HOUSEHOLD ENTITY"}
                      </span>
                      <h3 className="text-lg font-bold text-white tracking-tight">
                        {g.canonical_name}
                      </h3>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="text-[10px] font-mono text-slate-400">CLUSTER ID</span>
                    <div className="text-xs font-mono font-bold text-blue-400">
                      Cluster {g.cluster_id}
                    </div>
                  </div>
                </div>

                {/* Attributes Section */}
                <div className="mt-5 space-y-3.5 text-xs">
                  {/* Canonical Name */}
                  <div className="bg-[#161b22] border border-[#21262d] p-3 rounded-xl">
                    <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono mb-1">
                      <span>CANONICAL NAME</span>
                      <span className="text-emerald-400 font-semibold">
                        Source: Record {g.name_source_id}
                      </span>
                    </div>
                    <div className="text-sm font-bold text-white font-sans">{g.canonical_name}</div>
                    {g.aliases.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-[#21262d] flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-500">Aliases:</span>
                        {g.aliases.map((al, idx) => (
                          <span
                            key={idx}
                            className="bg-[#21262d] text-slate-300 font-mono text-[10px] px-2 py-0.5 rounded"
                          >
                            {al}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Primary Email */}
                  <div className="bg-[#161b22] border border-[#21262d] p-3 rounded-xl">
                    <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono mb-1">
                      <span className="flex items-center gap-1">
                        <Mail size={12} className="text-amber-400" /> PRIMARY EMAIL
                      </span>
                      <span className="text-amber-400 font-semibold">
                        Source: Record {g.email_source_id}
                      </span>
                    </div>
                    <div className="text-sm font-bold font-mono text-amber-300">{g.primary_email}</div>
                    {g.all_emails.length > 1 && (
                      <div className="mt-2 pt-2 border-t border-[#21262d] flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-500">Other Emails:</span>
                        {g.all_emails
                          .filter((e) => e !== g.primary_email)
                          .map((em, idx) => (
                            <span
                              key={idx}
                              className="bg-[#21262d] text-slate-300 font-mono text-[10px] px-2 py-0.5 rounded"
                            >
                              {em}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>

                  {/* Primary Phone */}
                  <div className="bg-[#161b22] border border-[#21262d] p-3 rounded-xl">
                    <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono mb-1">
                      <span className="flex items-center gap-1">
                        <Phone size={12} className="text-purple-400" /> PRIMARY PHONE
                      </span>
                      <span className="text-purple-400 font-semibold">
                        Source: Record {g.phone_source_id}
                      </span>
                    </div>
                    <div className="text-sm font-bold font-mono text-purple-300">{g.primary_phone}</div>
                    {g.all_phones.length > 1 && (
                      <div className="mt-2 pt-2 border-t border-[#21262d] flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] font-mono text-slate-500">Other Numbers:</span>
                        {g.all_phones
                          .filter((p) => p !== g.primary_phone)
                          .map((ph, idx) => (
                            <span
                              key={idx}
                              className="bg-[#21262d] text-slate-300 font-mono text-[10px] px-2 py-0.5 rounded"
                            >
                              {ph}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Card Footer Metrics */}
              <div className="mt-6 pt-4 border-t border-[#21262d] grid grid-cols-3 gap-2 text-center text-xs font-mono">
                <div className="bg-[#161b22] p-2 rounded-lg">
                  <div className="text-[10px] text-slate-500">MEMBERS</div>
                  <div className="font-bold text-white mt-0.5">{g.cluster_size} records</div>
                </div>
                <div className="bg-[#161b22] p-2 rounded-lg">
                  <div className="text-[10px] text-slate-500">CENTROID</div>
                  <div className="font-bold text-blue-400 mt-0.5">Record {g.centroid_id}</div>
                </div>
                <div className="bg-[#161b22] p-2 rounded-lg">
                  <div className="text-[10px] text-slate-500">CONFIDENCE</div>
                  <div className="font-bold text-emerald-400 mt-0.5">
                    {(g.average_confidence * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Centrality Leaderboard Table */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <span className="text-xs font-mono text-slate-300 font-semibold">
            FALKORDB GRAPHBLAS CENTRALITY &amp; DIMENSIONAL PAGERANK LEADERBOARD
          </span>
          <span className="text-[11px] font-mono text-slate-400">
            Computed via SuiteSparse:GraphBLAS
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#161b22]/70 text-slate-400 border-b border-[#21262d]">
              <tr>
                <th className="py-2.5 px-4">RECORD</th>
                <th className="py-2.5 px-4">NAME</th>
                <th className="py-2.5 px-4 text-center">COMPOSITE PR</th>
                <th className="py-2.5 px-4 text-center">NAME PR</th>
                <th className="py-2.5 px-4 text-center">EMAIL PR</th>
                <th className="py-2.5 px-4 text-center">PHONE PR</th>
                <th className="py-2.5 px-4 text-center">WEIGHTED DEGREE</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-slate-300">
              {(() => {
                const centroidIds = new Set(goldenEntities.filter(g => g.cluster_size > 1).map(g => g.centroid_id));
                return centrality.map((c) => {
                  const isCentroid = centroidIds.has(c.id);
                  return (
                    <tr
                      key={c.id}
                      className={`transition ${
                        isCentroid ? "bg-blue-950/30 hover:bg-blue-950/40 font-bold" : "hover:bg-[#161b22]/50"
                      }`}
                    >
                    <td className="py-3 px-4 font-bold text-blue-400">R{c.id}</td>
                    <td className="py-3 px-4 font-sans text-white">
                      {c.name}
                      {isCentroid && (
                        <span className="ml-2 text-[10px] font-mono font-normal bg-blue-600/30 text-blue-300 border border-blue-500/50 px-1.5 py-0.5 rounded">
                          CENTROID
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-emerald-400">
                      {(c.composite_pagerank ?? (c as any).pagerank ?? 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-300">
                      {(c.name_pagerank ?? 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-300">
                      {(c.email_pagerank ?? 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-300">
                      {(c.phone_pagerank ?? 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-indigo-300">
                      {(c.weighted_degree ?? 0).toFixed(3)}
                    </td>
                  </tr>
                );
              });
            })()}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
