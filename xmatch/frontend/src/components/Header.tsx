import React from "react";
import { Database, GitMerge, Cpu, ShieldCheck, Play, RefreshCw, Zap } from "lucide-react";
import { SystemStatus } from "../types";

interface HeaderProps {
  status: SystemStatus | null;
  threshold: number;
  onThresholdChange: (val: number) => void;
  onRunPipeline: () => void;
  loading: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  threshold,
  onThresholdChange,
  onRunPipeline,
  loading,
}) => {
  return (
    <header className="border-b border-[#21262d] bg-[#0d1117]/90 backdrop-blur-md sticky top-0 z-30 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand Title */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-bold">
            <GitMerge size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">xMatch Studio</h1>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-950/80 border border-blue-700/60 text-blue-300 font-medium">
                POC v0.1 &bull; xGraph Module
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Multi-Layer Identity Resolution, GraphBLAS Centrality & Golden Entity Synthesis
            </p>
          </div>
        </div>

        {/* System Badges */}
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#161b22] border border-[#30363d] text-slate-300">
            <span className={`w-2 h-2 rounded-full ${status?.falkordb_connected ? 'bg-emerald-400 shadow-sm shadow-emerald-400' : 'bg-red-400'}`} />
            <Database size={13} className="text-emerald-400" />
            <span className="font-mono">FalkorDB: {status?.falkordb_connected ? 'Active' : 'Offline'}</span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#161b22] border border-[#30363d] text-slate-300">
            <Zap size={13} className="text-amber-400" />
            <span className="font-mono">DuckDB: Ready</span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#161b22] border border-[#30363d] text-slate-300">
            <Cpu size={13} className="text-blue-400" />
            <span className="font-mono">GraphBLAS: Accelerated</span>
          </div>
        </div>

        {/* Pipeline Trigger & Threshold Control */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-[#161b22] border border-[#30363d] px-3 py-1.5 rounded-lg">
            <label className="text-xs text-slate-400 font-mono">Cutoff:</label>
            <input
              type="range"
              min="0.40"
              max="0.85"
              step="0.05"
              value={threshold}
              onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
              className="w-20 accent-blue-500 cursor-pointer h-1.5 bg-[#21262d] rounded-lg"
            />
            <span className="text-xs font-mono font-semibold text-blue-400 w-8 text-right">
              {threshold.toFixed(2)}
            </span>
          </div>

          <button
            onClick={onRunPipeline}
            disabled={loading}
            className="flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-2 rounded-lg shadow-md shadow-blue-600/25 transition active:scale-95"
          >
            {loading ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : (
              <Play size={14} className="fill-current" />
            )}
            <span>{loading ? "Computing..." : "Run Pipeline"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
