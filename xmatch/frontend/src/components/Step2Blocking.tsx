import React from "react";
import { Filter, CheckCircle2, TrendingDown, Terminal } from "lucide-react";
import { NormalizedRecord, CandidatePair } from "../types";

interface Step2BlockingProps {
  normalized: NormalizedRecord[];
  candidatePairs: CandidatePair[];
}

export const Step2Blocking: React.FC<Step2BlockingProps> = ({
  normalized,
  candidatePairs,
}) => {
  const blockingSql = `-- Step 2: Multi-Pass Inverted Index Blocking Queries in DuckDB
CREATE OR REPLACE TABLE candidate_pairs AS
WITH pass_phone_prefix AS (
    SELECT a.id AS id1, b.id AS id2, 'phone_prefix_4' AS rule
    FROM records a JOIN records b ON a.phone_prefix_4 = b.phone_prefix_4 AND a.id < b.id
    WHERE a.phone_prefix_4 <> ''
),
pass_phone_suffix AS (
    SELECT a.id AS id1, b.id AS id2, 'phone_suffix_4' AS rule
    FROM records a JOIN records b ON a.phone_suffix_4 = b.phone_suffix_4 AND a.id < b.id
    WHERE a.phone_suffix_4 <> ''
),
pass_email_prefix AS (
    SELECT a.id AS id1, b.id AS id2, 'email_user_prefix_4' AS rule
    FROM records a JOIN records b ON a.email_user_prefix_4 = b.email_user_prefix_4 AND a.id < b.id
    WHERE a.email_user_prefix_4 <> ''
),
pass_token_match AS (
    SELECT a.id AS id1, b.id AS id2, 'token_match' AS rule
    FROM records a JOIN records b ON (a.first_token = b.first_token OR a.last_token = b.last_token) AND a.id < b.id
)
SELECT id1, id2, STRING_AGG(rule, '; ') AS triggered_rules
FROM (
    SELECT * FROM pass_phone_prefix UNION ALL
    SELECT * FROM pass_phone_suffix UNION ALL
    SELECT * FROM pass_email_prefix UNION ALL
    SELECT * FROM pass_token_match
)
GROUP BY id1, id2;`;

  return (
    <div className="space-y-6">
      {/* Reduction Metrics Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#161b22] border border-[#30363d] p-4 rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400">NAIVE CARTESIAN PAIRS</div>
            <div className="text-xl font-bold font-mono text-red-400 mt-0.5">6 pairs (100%)</div>
            <div className="text-[10px] text-slate-500 font-mono mt-0.5">O(N²) quadratic scaling</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-red-950/60 border border-red-800/60 flex items-center justify-center text-red-400">
            <TrendingDown size={18} />
          </div>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] p-4 rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400">FILTERED CANDIDATES</div>
            <div className="text-xl font-bold font-mono text-emerald-400 mt-0.5">
              {candidatePairs.length} pairs
            </div>
            <div className="text-[10px] text-slate-500 font-mono mt-0.5">DuckDB inverted indexes</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-950/60 border border-emerald-800/60 flex items-center justify-center text-emerald-400">
            <CheckCircle2 size={18} />
          </div>
        </div>

        <div className="bg-[#161b22] border border-[#30363d] p-4 rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] font-mono text-slate-400">AT 1 BILLION SCALE</div>
            <div className="text-xl font-bold font-mono text-blue-400 mt-0.5">500M × 10¹⁸ → 5B</div>
            <div className="text-[10px] text-slate-500 font-mono mt-0.5">99.999% reduction ratio</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-blue-950/60 border border-blue-800/60 flex items-center justify-center text-blue-400">
            <Filter size={18} />
          </div>
        </div>
      </div>

      {/* Normalized Features Table */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <span className="text-xs font-mono text-slate-300 font-semibold">
            TABLE: records_normalized (Vectorized Extraction)
          </span>
          <span className="text-[11px] font-mono text-slate-400">Generated in &lt;1ms</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#161b22]/70 text-slate-400 font-mono border-b border-[#21262d]">
              <tr>
                <th className="py-2.5 px-4">ID</th>
                <th className="py-2.5 px-4">PHONE 7</th>
                <th className="py-2.5 px-4">PHONE PRE-4</th>
                <th className="py-2.5 px-4">PHONE SUF-4</th>
                <th className="py-2.5 px-4">EMAIL USER PRE-4</th>
                <th className="py-2.5 px-4">FIRST TOKEN</th>
                <th className="py-2.5 px-4">LAST TOKEN</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-slate-300 font-mono">
              {normalized.map((n) => (
                <tr key={n.id} className="hover:bg-[#161b22]/50 transition">
                  <td className="py-2.5 px-4 font-bold text-blue-400">R{n.id}</td>
                  <td className="py-2.5 px-4 text-emerald-300">{n.phone_7}</td>
                  <td className="py-2.5 px-4 text-slate-300">{n.phone_prefix_4}</td>
                  <td className="py-2.5 px-4 text-slate-300">{n.phone_suffix_4}</td>
                  <td className="py-2.5 px-4 text-amber-300">{n.email_user_prefix_4}</td>
                  <td className="py-2.5 px-4 text-slate-200">{n.first_token}</td>
                  <td className="py-2.5 px-4 text-slate-200">{n.last_token}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Triggered Candidates Table */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <span className="text-xs font-mono text-slate-300 font-semibold">
            TABLE: candidate_pairs (Output of Multi-Pass Blocking)
          </span>
          <span className="text-[11px] font-mono text-emerald-400">{candidatePairs.length} candidate edges passed to scoring</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#161b22]/70 text-slate-400 font-mono border-b border-[#21262d]">
              <tr>
                <th className="py-2.5 px-4">CANDIDATE PAIR</th>
                <th className="py-2.5 px-4">TRIGGERED BLOCKING PASSES</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-slate-300 font-mono">
              {candidatePairs.map((c, idx) => (
                <tr key={idx} className="hover:bg-[#161b22]/50 transition">
                  <td className="py-2.5 px-4 font-bold text-blue-400">
                    (R{c.id1}, R{c.id2})
                  </td>
                  <td className="py-2.5 px-4 text-slate-300">
                    <span className="bg-[#21262d] border border-[#30363d] px-2 py-0.5 rounded text-[11px] text-indigo-300">
                      {c.rules}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* SQL Blocking Query */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <div className="flex items-center gap-2 text-slate-300 text-xs font-mono font-semibold">
            <Terminal size={14} className="text-blue-400" />
            DuckDB Multi-Pass Inverted Index SQL
          </div>
          <span className="text-[11px] text-slate-400 font-mono">Parallel Bitmapped Joins</span>
        </div>
        <div className="p-4 bg-[#070a0f] overflow-x-auto">
          <pre className="text-xs font-mono text-cyan-300 leading-relaxed">
            {blockingSql}
          </pre>
        </div>
      </div>
    </div>
  );
};
