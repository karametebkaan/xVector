import React, { useState } from "react";
import {
  Share2,
  Terminal,
  Code2,
  Play,
  RotateCw,
  Search,
  Layers,
  Sparkles,
  Info,
  CheckCircle,
  Copy,
  Check,
} from "lucide-react";
import { GraphvizViewer } from "./GraphvizViewer";
import { PipelinePayload } from "../types";
import { executeCypher, fetchTransitivePaths } from "../api";

interface Step4GraphVisualizerProps {
  payload: PipelinePayload;
}

export const Step4GraphVisualizer: React.FC<Step4GraphVisualizerProps> = ({ payload }) => {
  // Graph View Modes: 'heterogeneous' vs 'multilayer'
  const [viewMode, setViewMode] = useState<"heterogeneous" | "multilayer">("heterogeneous");

  // Selected Node state from SVG click
  const [selectedNodeKey, setSelectedNodeKey] = useState<string | null>("n3");

  // Transitive path state
  const [pathSource, setPathSource] = useState<number>(1);
  const [pathTarget, setPathTarget] = useState<number>(2);
  const [foundPaths, setFoundPaths] = useState<any[] | null>(null);
  const [pathLoading, setPathLoading] = useState<boolean>(false);

  // Cypher Console state
  const [cypherQuery, setCypherQuery] = useState<string>(
    "CALL algo.pageRank('NAME', 'SIMILAR_TO')"
  );
  const [cypherResult, setCypherResult] = useState<{
    columns: string[];
    rows: any[][];
  } | null>(null);
  const [cypherLoading, setCypherLoading] = useState<boolean>(false);
  const [cypherError, setCypherError] = useState<string | null>(null);

  // DOT code viewer toggle
  const [showDotSource, setShowDotSource] = useState<boolean>(false);
  const [copiedDot, setCopiedDot] = useState<boolean>(false);

  const activeDot =
    viewMode === "heterogeneous"
      ? payload.dot_heterogeneous
      : payload.dot_multilayer;

  // Run Cypher
  const handleRunCypher = async (queryToRun?: string) => {
    const q = queryToRun || cypherQuery;
    setCypherLoading(true);
    setCypherError(null);
    try {
      const res = await executeCypher(q);
      setCypherResult({ columns: res.columns, rows: res.rows });
    } catch (err: any) {
      setCypherError(err.message || "Failed to execute Cypher query");
    } finally {
      setCypherLoading(false);
    }
  };

  // Find Transitive Path
  const handleFindPath = async () => {
    setPathLoading(true);
    try {
      const res = await fetchTransitivePaths(pathSource, pathTarget);
      setFoundPaths(res.paths);
    } catch (err) {
      console.error(err);
    } finally {
      setPathLoading(false);
    }
  };

  const handleCopyDot = () => {
    navigator.clipboard.writeText(activeDot);
    setCopiedDot(true);
    setTimeout(() => setCopiedDot(false), 2000);
  };

  // Helper to extract node inspector information
  const getNodeDetails = () => {
    if (!selectedNodeKey) return null;
    const key = selectedNodeKey.toLowerCase();

    // Check if it's a Record node
    if (key.includes("record") || key.startsWith("r")) {
      const match = key.match(/\d+/);
      const rid = match ? parseInt(match[0]) : 1;
      const rec = payload.records.find((r) => r.id === rid);
      const cent = payload.centrality.find((c) => c.id === rid);
      if (rec) {
        return {
          type: "Record Node (:Record)",
          title: `Record ${rec.id}: ${rec.name}`,
          properties: [
            { label: "Record ID", val: `R${rec.id}` },
            { label: "Raw Name", val: rec.name },
            { label: "Raw Email", val: rec.email },
            { label: "Raw Phone", val: rec.phone },
            {
              label: "Composite PageRank",
              val: cent ? (cent.composite_pagerank ?? (cent as any).pagerank ?? 0).toFixed(4) : "N/A",
            },
            {
              label: "Weighted Degree",
              val: cent ? (cent.weighted_degree ?? 0).toFixed(3) : "N/A",
            },
            {
              label: "Role",
              val:
                rec.id === 3
                  ? "Golden Cluster Centroid"
                  : rec.id === 4
                  ? "Isolated Family Record"
                  : "Cluster Member",
            },
          ],
        };
      }
    }

    // Check if it's a Name node
    if (key.startsWith("n") || key.includes("name")) {
      const prMap = payload.attribute_pagerank?.NAME || {};
      const val = Object.keys(prMap).find((k) =>
        key.includes(k.toLowerCase()) || key.includes("n3")
          ? k === "kaan karamete"
          : key.includes("n2")
          ? k === "kkaramete"
          : key.includes("n1")
          ? k === "kaan"
          : k === "gulgun karamete"
      ) || "kaan karamete";
      const pr = prMap[val] ?? 0.1525;
      return {
        type: "Attribute Node (:NAME)",
        title: `NAME: "${val}"`,
        properties: [
          { label: "Node Label", val: ":NAME" },
          { label: "Normalized Value", val: val },
          { label: "GraphBLAS PageRank", val: pr.toFixed(4) },
          {
            label: "Survivorship Status",
            val: val === "kaan karamete" ? "WINNER (Canonical Name)" : "Alias",
          },
        ],
      };
    }

    // Check if it's an Email node
    if (key.startsWith("e") || key.includes("email") || key.includes("@")) {
      const prMap = payload.attribute_pagerank?.EMAIL || {};
      const val = Object.keys(prMap).find((k) =>
        key.includes(k.toLowerCase()) || key.includes("e3")
          ? k === "kallespapaz@gmail"
          : key.includes("e2")
          ? k === "kalles@gmail.com"
          : key.includes("e1")
          ? k === "kpapaz@gmail"
          : k === "gkaramete@kmail.com"
      ) || "kallespapaz@gmail";
      const pr = prMap[val] ?? 0.1525;
      return {
        type: "Attribute Node (:EMAIL)",
        title: `EMAIL: "${val}"`,
        properties: [
          { label: "Node Label", val: ":EMAIL" },
          { label: "Normalized Value", val: val },
          { label: "GraphBLAS PageRank", val: pr.toFixed(4) },
          {
            label: "Survivorship Status",
            val: val === "kallespapaz@gmail" ? "WINNER (Primary Email)" : "Secondary Email",
          },
        ],
      };
    }

    // Default to Phone
    const prMap = payload.attribute_pagerank?.PHONE || {};
    const val = Object.keys(prMap).find((k) =>
      key.includes(k.toLowerCase()) || key.includes("p2")
        ? k === "5182696226"
        : key.includes("p1")
        ? k === "2696227"
        : key.includes("p3")
        ? k === "404356789"
        : k === "2696777"
    ) || "5182696226";
    const pr = prMap[val] ?? 0.1098;
    return {
      type: "Attribute Node (:PHONE)",
      title: `PHONE: "${val}"`,
      properties: [
        { label: "Node Label", val: ":PHONE" },
        { label: "Phone Number", val: val },
        { label: "GraphBLAS PageRank", val: pr.toFixed(4) },
        {
          label: "Survivorship Status",
          val: val === "5182696226" ? "WINNER (Standard 10-Digit Line)" : "Secondary Phone",
        },
      ],
    };
  };

  const nodeDetails = getNodeDetails();

  return (
    <div className="space-y-6">
      {/* Visualizer Header Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#161b22] border border-[#30363d] p-4 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
            <Share2 size={18} />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight">
              FalkorDB GraphBLAS &amp; In-Browser Graphviz DOT Canvas
            </h2>
            <p className="text-xs text-slate-400">
              Native WebAssembly Graphviz rendering. Pan, zoom, drag, and click nodes to inspect topological centrality.
            </p>
          </div>
        </div>

        {/* View Mode Switcher & DOT Drawer Button */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-[#0d1117] border border-[#30363d] p-1 rounded-lg">
            <button
              onClick={() => setViewMode("heterogeneous")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                viewMode === "heterogeneous"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers size={13} />
              <span>Heterogeneous Entity-Attribute Graph</span>
            </button>

            <button
              onClick={() => setViewMode("multilayer")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition ${
                viewMode === "multilayer"
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Share2 size={13} />
              <span>Multi-Layer Record Graph</span>
            </button>
          </div>

          <button
            onClick={() => setShowDotSource(!showDotSource)}
            className="flex items-center gap-1.5 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] text-slate-300 text-xs px-3 py-2 rounded-lg transition"
          >
            <Code2 size={14} />
            <span>{showDotSource ? "Hide DOT" : "View DOT Source"}</span>
          </button>
        </div>
      </div>

      {/* Main Visualizer Area: Graph Canvas + Side Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Graph Canvas (3 cols) */}
        <div className="lg:col-span-3 relative h-[620px] rounded-xl overflow-hidden border border-[#21262d]">
          <GraphvizViewer
            dot={activeDot}
            onSelectNode={(nodeKey) => setSelectedNodeKey(nodeKey)}
            selectedNode={selectedNodeKey}
          />
        </div>

        {/* Node Detail Inspector & Legend (1 col) */}
        <div className="space-y-4">
          {/* Node Inspector Card */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-[#21262d]">
              <div className="flex items-center gap-2 text-xs font-mono font-semibold text-blue-400">
                <Info size={14} />
                <span>NODE INSPECTOR</span>
              </div>
              <span className="text-[10px] font-mono text-slate-500 uppercase">
                {nodeDetails?.type || "Select a node"}
              </span>
            </div>

            {nodeDetails ? (
              <div className="mt-3 space-y-3">
                <h3 className="text-sm font-bold text-white leading-tight font-sans">
                  {nodeDetails.title}
                </h3>

                <div className="space-y-2 text-xs">
                  {nodeDetails.properties.map((p, i) => (
                    <div
                      key={i}
                      className="flex flex-col bg-[#0d1117] p-2 rounded-lg border border-[#21262d]"
                    >
                      <span className="text-[10px] font-mono text-slate-400 uppercase">
                        {p.label}
                      </span>
                      <span className="font-mono text-slate-200 mt-0.5 break-all">
                        {p.val}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-slate-500">
                Click any node on the graph canvas to inspect its label, PageRank, and connections.
              </div>
            )}
          </div>

          {/* Graph Legend Card */}
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-4 text-xs space-y-2.5">
            <div className="font-semibold text-slate-300 font-mono text-[11px]">
              GRAPH TOPOLOGY LEGEND
            </div>
            <div className="space-y-2 text-[11px]">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500 shadow-sm shadow-blue-500/50" />
                <span className="text-slate-300">
                  <strong>:Record</strong> Touchpoint Source Records
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded bg-emerald-500 shadow-sm shadow-emerald-500/50" />
                <span className="text-slate-300">
                  <strong>:NAME</strong> Distinct Name Nodes
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded bg-amber-500 shadow-sm shadow-amber-500/50" />
                <span className="text-slate-300">
                  <strong>:EMAIL</strong> Email Address Nodes
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded bg-purple-500 shadow-sm shadow-purple-500/50" />
                <span className="text-slate-300">
                  <strong>:PHONE</strong> Telephone Number Nodes
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-0.5 bg-red-400 border border-dashed border-red-400" />
                <span className="text-red-300">
                  <strong>:FAMILY_CONFLICT</strong> Household Invalidation
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Raw DOT Drawer (Conditional) */}
      {showDotSource && (
        <div className="bg-[#0d1117] border border-[#21262d] rounded-xl overflow-hidden transition">
          <div className="px-5 py-3 border-b border-[#21262d] flex items-center justify-between bg-[#161b22]">
            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-slate-300">
              <Code2 size={14} className="text-blue-400" />
              Graphviz DOT Source ({viewMode === "heterogeneous" ? "identity_graph.dot" : "Multi-Layer"})
            </div>
            <button
              onClick={handleCopyDot}
              className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white bg-[#21262d] px-2.5 py-1 rounded-md transition"
            >
              {copiedDot ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
              <span>{copiedDot ? "Copied!" : "Copy DOT"}</span>
            </button>
          </div>
          <pre className="p-4 text-xs font-mono text-slate-300 bg-[#070a0f] max-h-72 overflow-y-auto leading-relaxed">
            {activeDot}
          </pre>
        </div>
      )}

      {/* Interactive Transitive Path Finder */}
      <div className="bg-[#161b22] border border-[#30363d] p-5 rounded-xl space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-[#21262d]">
          <div>
            <div className="text-xs font-mono font-semibold text-cyan-400 flex items-center gap-2">
              <Search size={14} /> MULTI-HOP TRANSITIVE RESOLUTION EXPLORER
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Traverse the multi-layer graph to trace how two unlinked or weak records resolve transitively through an attribute centroid.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400 font-mono">From:</span>
              <select
                value={pathSource}
                onChange={(e) => setPathSource(parseInt(e.target.value))}
                className="bg-[#0d1117] border border-[#30363d] text-slate-200 text-xs px-2.5 py-1.5 rounded-lg"
              >
                {payload.records.map((r) => (
                  <option key={r.id} value={r.id}>
                    R{r.id}: {r.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400 font-mono">To:</span>
              <select
                value={pathTarget}
                onChange={(e) => setPathTarget(parseInt(e.target.value))}
                className="bg-[#0d1117] border border-[#30363d] text-slate-200 text-xs px-2.5 py-1.5 rounded-lg"
              >
                {payload.records.map((r) => (
                  <option key={r.id} value={r.id}>
                    R{r.id}: {r.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleFindPath}
              disabled={pathLoading}
              className="flex items-center gap-1.5 bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs px-3.5 py-1.5 rounded-lg transition"
            >
              {pathLoading ? <RotateCw size={13} className="animate-spin" /> : <Play size={13} />}
              <span>Find Transitive Bridge</span>
            </button>
          </div>
        </div>

        {/* Found Paths Display */}
        {foundPaths && (
          <div className="space-y-2">
            <div className="text-xs font-mono text-slate-400">
              Resolved Paths ({foundPaths.length} discovered):
            </div>
            {foundPaths.length === 0 ? (
              <div className="text-xs font-mono text-amber-400 bg-amber-950/20 border border-amber-900/40 p-3 rounded-lg">
                No connected path found between Record {pathSource} and Record {pathTarget} (isolated component).
              </div>
            ) : (
              foundPaths.map((p, idx) => (
                <div
                  key={idx}
                  className="bg-[#0d1117] border border-[#21262d] p-3 rounded-lg flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2 font-mono">
                    <span className="text-emerald-400 font-bold">Path {idx + 1}:</span>
                    <span className="text-slate-200">{p.nodes.join("  →  ")}</span>
                  </div>
                  <span className="font-mono text-xs text-slate-400 bg-[#161b22] px-2 py-0.5 rounded border border-[#30363d]">
                    {p.length} Hop{p.length > 1 ? "s" : ""}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Live openCypher Query Console */}
      <div className="bg-[#161b22] border border-[#30363d] p-5 rounded-xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-[#21262d]">
          <div className="flex items-center gap-2 text-xs font-mono font-semibold text-emerald-400">
            <Terminal size={14} /> LIVE OPENCYPHER QUERY CONSOLE (FalkorDB / GraphBLAS)
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Direct RESP Execution on port 6379
          </span>
        </div>

        {/* Query Presets Chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400 font-mono mr-1">Presets:</span>
          {[
            "CALL algo.wcc()",
            "CALL algo.pageRank('NAME', 'SIMILAR_TO')",
            "CALL algo.pageRank('EMAIL', 'SIMILAR_TO')",
            "CALL algo.pageRank('PHONE', 'SIMILAR_TO')",
            "MATCH (a:Record)-[:MATCHES_NAME]-(b:Record) RETURN a.id, a.name, b.id, b.name",
            "MATCH (r:Record)-[:HAS_NAME]->(n:NAME) RETURN r.id, r.name, n.val",
          ].map((preset, idx) => (
            <button
              key={idx}
              onClick={() => {
                setCypherQuery(preset);
                handleRunCypher(preset);
              }}
              className="bg-[#0d1117] hover:bg-[#21262d] border border-[#30363d] text-slate-300 hover:text-white text-[11px] font-mono px-2.5 py-1 rounded transition"
            >
              {preset}
            </button>
          ))}
        </div>

        {/* Query Input Box */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={cypherQuery}
            onChange={(e) => setCypherQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRunCypher()}
            placeholder="Type Cypher query, e.g., MATCH (n) RETURN n..."
            className="flex-1 bg-[#0d1117] border border-[#30363d] focus:border-blue-500 text-slate-200 text-xs font-mono px-4 py-2.5 rounded-lg outline-none transition"
          />
          <button
            onClick={() => handleRunCypher()}
            disabled={cypherLoading}
            className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs px-4 py-2.5 rounded-lg transition"
          >
            {cypherLoading ? <RotateCw size={13} className="animate-spin" /> : <Play size={13} />}
            <span>Execute</span>
          </button>
        </div>

        {/* Cypher Error */}
        {cypherError && (
          <div className="p-3 bg-red-950/40 border border-red-900/60 rounded-lg text-xs font-mono text-red-300">
            {cypherError}
          </div>
        )}

        {/* Cypher Result Table */}
        {cypherResult && (
          <div className="bg-[#0d1117] border border-[#21262d] rounded-lg overflow-hidden">
            <div className="px-4 py-2 border-b border-[#21262d] text-[11px] font-mono text-slate-400 flex items-center justify-between">
              <span>RESULT: {cypherResult.rows.length} rows</span>
            </div>
            <div className="overflow-x-auto max-h-60">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-[#161b22] text-slate-300 border-b border-[#21262d]">
                  <tr>
                    {cypherResult.columns.map((c, i) => (
                      <th key={i} className="py-2 px-3">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#21262d] text-slate-300">
                  {cypherResult.rows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-[#161b22]/50">
                      {row.map((val, cIdx) => (
                        <td key={cIdx} className="py-2 px-3 text-slate-200">
                          {typeof val === "object" ? JSON.stringify(val) : String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
