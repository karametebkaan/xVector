import React from "react";
import { Database, Filter, Gauge, Share2, Award, Sparkles } from "lucide-react";

interface PipelineStepperProps {
  activeStep: number;
  onSelectStep: (step: number) => void;
}

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  activeStep,
  onSelectStep,
}) => {
  const steps = [
    { id: 1, title: "1. Raw Data Lake", icon: Database, desc: "Source Table & Ingest" },
    { id: 2, title: "2. Vectorized Blocking", icon: Filter, desc: "O(N²) Elimination" },
    { id: 3, title: "3. Similarity Matrix", icon: Gauge, desc: "Multi-Column Scoring" },
    { id: 4, title: "4. FalkorDB Graph & DOT", icon: Share2, desc: "Interactive Visualizer" },
    { id: 5, title: "5. Golden Entity Master", icon: Award, desc: "Master Survivorship" },
    { id: 6, title: "6. Vector Benchmark", icon: Sparkles, desc: "Failure Modes & Risks" },
  ];

  return (
    <div className="bg-[#0d1117] border-b border-[#21262d] py-2 px-6">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-1 overflow-x-auto scrollbar-none">
        {steps.map((s) => {
          const Icon = s.icon;
          const isActive = activeStep === s.id;
          return (
            <button
              key={s.id}
              onClick={() => onSelectStep(s.id)}
              className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg text-left transition whitespace-nowrap ${
                isActive
                  ? "bg-blue-600/15 border border-blue-500/40 text-blue-400 font-medium shadow-sm"
                  : "hover:bg-[#161b22] text-slate-400 hover:text-slate-200 border border-transparent"
              }`}
            >
              <div
                className={`w-7 h-7 rounded-md flex items-center justify-center text-xs ${
                  isActive
                    ? "bg-blue-600 text-white shadow-sm shadow-blue-500/50"
                    : "bg-[#21262d] text-slate-400"
                }`}
              >
                <Icon size={14} />
              </div>
              <div className="text-left">
                <div className="text-xs font-semibold leading-tight">{s.title}</div>
                <div className="text-[10px] text-slate-500 font-mono leading-tight">{s.desc}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
