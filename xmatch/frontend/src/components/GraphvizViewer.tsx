import React, { useEffect, useRef, useState, useCallback } from "react";
import type { Graphviz } from "@hpcc-js/wasm-graphviz";
import { ZoomIn, ZoomOut, RotateCcw, Maximize2, Move } from "lucide-react";

let graphvizPromise: Promise<Graphviz> | null = null;
function loadGraphviz(): Promise<Graphviz> {
  if (!graphvizPromise) {
    graphvizPromise = import("@hpcc-js/wasm-graphviz").then((m) => m.Graphviz.load());
  }
  return graphvizPromise;
}

interface GraphvizViewerProps {
  dot: string;
  onSelectNode?: (nodeLabel: string) => void;
  selectedNode?: string | null;
}

export const GraphvizViewer: React.FC<GraphvizViewerProps> = ({
  dot,
  onSelectNode,
  selectedNode,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [svgHtml, setSvgHtml] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Transform state for pan & zoom
  const [transform, setTransform] = useState<{ x: number; y: number; scale: number }>({
    x: 0,
    y: 0,
    scale: 0.9,
  });
  const isDragging = useRef<boolean>(false);
  const dragStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Render DOT via WASM
  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError(null);

    loadGraphviz()
      .then((gv) => {
        if (isCancelled) return;
        try {
          const rawSvg = gv.dot(dot);
          setSvgHtml(rawSvg);
          setLoading(false);
        } catch (err: any) {
          setError(err.message || "Failed to render DOT graph");
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isCancelled) return;
        setError(err.message || "Failed to load Graphviz WASM");
        setLoading(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [dot]);

  // Attach click listeners to SVG nodes once rendered
  useEffect(() => {
    if (!contentRef.current || !svgHtml) return;

    const nodeElements = contentRef.current.querySelectorAll("g.node");
    nodeElements.forEach((el) => {
      const titleEl = el.querySelector("title");
      const textEls = Array.from(el.querySelectorAll("text"));
      const labelText = textEls.map((t) => t.textContent?.trim() || "").join(" ").trim();
      const nodeKey = titleEl?.textContent?.trim() || labelText;

      const clickHandler = (e: Event) => {
        e.stopPropagation();
        if (onSelectNode) {
          onSelectNode(nodeKey);
        }
      };

      el.addEventListener("click", clickHandler);
    });
  }, [svgHtml, onSelectNode]);

  // Pan and drag handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // only left click
    isDragging.current = true;
    dragStart.current = { x: e.clientX - transform.x, y: e.clientY - transform.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging.current) return;
    setTransform((prev) => ({
      ...prev,
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
    }));
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    setTransform((prev) => ({
      ...prev,
      scale: Math.max(0.1, Math.min(prev.scale * zoomFactor, 5)),
    }));
  };

  const zoomIn = () => setTransform((p) => ({ ...p, scale: Math.min(p.scale * 1.25, 5) }));
  const zoomOut = () => setTransform((p) => ({ ...p, scale: Math.max(p.scale * 0.8, 0.1) }));
  const resetZoom = () => setTransform({ x: 0, y: 0, scale: 0.85 });

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      className="relative w-full h-full min-h-[550px] bg-[#070a0f] border border-[#21262d] rounded-xl overflow-hidden cursor-grab active:cursor-grabbing select-none"
    >
      {/* Floating Toolbar */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-1.5 bg-[#161b22]/90 backdrop-blur-md border border-[#30363d] px-2 py-1.5 rounded-lg shadow-xl text-slate-300">
        <button
          onClick={zoomIn}
          title="Zoom In"
          className="p-1.5 hover:bg-[#21262d] hover:text-white rounded transition"
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={zoomOut}
          title="Zoom Out"
          className="p-1.5 hover:bg-[#21262d] hover:text-white rounded transition"
        >
          <ZoomOut size={16} />
        </button>
        <button
          onClick={resetZoom}
          title="Reset View"
          className="p-1.5 hover:bg-[#21262d] hover:text-white rounded transition"
        >
          <RotateCcw size={16} />
        </button>
        <div className="h-4 w-[1px] bg-[#30363d] mx-1" />
        <span className="text-xs font-mono text-slate-400 px-1">
          {Math.round(transform.scale * 100)}%
        </span>
      </div>

      {/* Floating Instructions Pill */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2 bg-[#161b22]/80 backdrop-blur border border-[#30363d] px-3 py-1.5 rounded-full text-xs text-slate-400">
        <Move size={13} className="text-blue-400" />
        <span>Drag to pan &bull; Scroll to zoom &bull; Click any node to inspect</span>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-[#070a0f]/80 backdrop-blur-sm">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
          <p className="text-xs text-slate-400 font-mono">Compiling Graphviz DOT in WebAssembly...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 text-center">
          <div className="bg-red-950/60 border border-red-800 text-red-200 px-4 py-3 rounded-xl max-w-lg">
            <h4 className="font-semibold text-sm mb-1">Graphviz Rendering Error</h4>
            <p className="text-xs font-mono text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* SVG Canvas Container */}
      <div
        ref={contentRef}
        style={{
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
          transformOrigin: "center center",
          transition: isDragging.current ? "none" : "transform 0.05s ease-out",
        }}
        className="graphviz-svg-container w-full h-full flex items-center justify-center p-8 pointer-events-auto"
        dangerouslySetInnerHTML={{ __html: svgHtml }}
      />
    </div>
  );
};
