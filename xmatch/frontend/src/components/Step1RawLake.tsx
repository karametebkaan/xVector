import React from "react";
import { Database, Code, CheckCircle } from "lucide-react";
import { RecordItem } from "../types";

interface Step1RawLakeProps {
  records: RecordItem[];
}

export const Step1RawLake: React.FC<Step1RawLakeProps> = ({ records }) => {
  const sqlCode = `-- Step 1: Raw Data Lake Ingestion into DuckDB / BigQuery
CREATE OR REPLACE TABLE raw_touchpoint_records AS
SELECT 
    id,
    TRIM(name) AS name,
    LOWER(TRIM(email)) AS email,
    REGEXP_REPLACE(phone, '[^0-9]', '', 'g') AS phone
FROM read_parquet('gs://identity_lake/touchpoints/*.parquet')
WHERE name IS NOT NULL;`;

  return (
    <div className="space-y-6">
      {/* Intro Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#161b22] border border-[#30363d] p-5 rounded-xl">
        <div>
          <div className="flex items-center gap-2 text-blue-400 text-xs font-mono font-semibold uppercase tracking-wider mb-1">
            <Database size={14} /> Stage 1: Data Lake Ingestion
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">Source Touchpoint Records</h2>
          <p className="text-xs text-slate-400 mt-1">
            Raw disparate records ingested from distributed operational systems, CRM, and log data.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-mono text-slate-300">
          <div className="bg-[#21262d] px-3 py-1.5 rounded-lg border border-[#30363d]">
            Total Ingested: <span className="text-emerald-400 font-bold">{records.length} records</span>
          </div>
        </div>
      </div>

      {/* Records Table */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400 font-medium">TABLE: raw_touchpoints</span>
          <span className="text-[11px] font-mono text-slate-500">4 rows &bull; 4 columns</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#161b22] text-slate-300 font-mono border-b border-[#21262d]">
              <tr>
                <th className="py-2.5 px-4">RECORD ID</th>
                <th className="py-2.5 px-4">NAME</th>
                <th className="py-2.5 px-4">EMAIL</th>
                <th className="py-2.5 px-4">PHONE</th>
                <th className="py-2.5 px-4">GROUND TRUTH IDENTITY</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#21262d] text-slate-300">
              {records.map((r) => {
                const isKaan = r.id <= 3;
                return (
                  <tr key={r.id} className="hover:bg-[#161b22]/50 transition">
                    <td className="py-3 px-4 font-mono font-bold text-blue-400">
                      R{r.id}
                    </td>
                    <td className="py-3 px-4 font-medium text-white">
                      {r.name}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {r.email}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {r.phone}
                    </td>
                    <td className="py-3 px-4">
                      {isKaan ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-blue-950/80 border border-blue-700/60 text-blue-300">
                          <CheckCircle size={11} className="text-blue-400" />
                          Individual: Kaan Karamete
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-amber-950/80 border border-amber-700/60 text-amber-300">
                          Individual: Gulgun Karamete (Family Member)
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* SQL Extraction Block */}
      <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
          <div className="flex items-center gap-2 text-slate-300 text-xs font-mono font-semibold">
            <Code size={14} className="text-amber-400" />
            Columnar Ingestion Query (DuckDB / BigQuery SQL)
          </div>
          <span className="text-[11px] text-slate-400 font-mono">Dialect: DuckDB 1.5.5</span>
        </div>
        <div className="p-4 bg-[#070a0f] overflow-x-auto">
          <pre className="text-xs font-mono text-emerald-400 leading-relaxed">
            {sqlCode}
          </pre>
        </div>
      </div>
    </div>
  );
};
