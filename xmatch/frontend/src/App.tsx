import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { PipelineStepper } from "./components/PipelineStepper";
import { Step1RawLake } from "./components/Step1RawLake";
import { Step2Blocking } from "./components/Step2Blocking";
import { Step3Scoring } from "./components/Step3Scoring";
import { Step4GraphVisualizer } from "./components/Step4GraphVisualizer";
import { Step5GoldenMaster } from "./components/Step5GoldenMaster";
import { Step6Benchmark } from "./components/Step6Benchmark";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { fetchSystemStatus, fetchPipelineData, runPipelineWithParams } from "./api";
import { SystemStatus, PipelinePayload } from "./types";
import { AlertCircle, RefreshCw } from "lucide-react";

export function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [payload, setPayload] = useState<PipelinePayload | null>(null);
  const [activeStep, setActiveStep] = useState<number>(4); // default to Step 4 (Graph Visualizer)
  const [threshold, setThreshold] = useState<number>(0.60);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Initial load
  useEffect(() => {
    async function init() {
      setLoading(true);
      setError(null);
      try {
        const [sysStatus, pipeData] = await Promise.all([
          fetchSystemStatus(),
          fetchPipelineData(0.60),
        ]);
        setStatus(sysStatus);
        setPayload(pipeData);
      } catch (err: any) {
        console.error("Initialization error:", err);
        setError(err.message || "Failed to connect to xMatch API");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // Run pipeline trigger
  const handleRunPipeline = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await runPipelineWithParams(threshold);
      setPayload(data);
    } catch (err: any) {
      console.error("Pipeline run error:", err);
      setError(err.message || "Failed to re-run pipeline");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070a0f] text-slate-100 flex flex-col">
      {/* Top Header */}
      <Header
        status={status}
        threshold={threshold}
        onThresholdChange={setThreshold}
        onRunPipeline={handleRunPipeline}
        loading={loading}
      />

      {/* Step Navigation Bar */}
      <PipelineStepper
        activeStep={activeStep}
        onSelectStep={(step) => setActiveStep(step)}
      />

      {/* Main Content Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {error && (
          <div className="mb-6 bg-red-950/60 border border-red-800 p-4 rounded-xl flex items-center justify-between text-red-200 text-xs">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-red-400 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={handleRunPipeline}
              className="bg-red-900/60 hover:bg-red-800 text-red-100 px-3 py-1.5 rounded-lg font-mono"
            >
              Retry
            </button>
          </div>
        )}

        {loading && !payload ? (
          <div className="h-96 flex flex-col items-center justify-center text-slate-400 space-y-3">
            <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <div className="text-sm font-mono text-slate-300">
              Initializing FalkorDB GraphBLAS &amp; DuckDB engines...
            </div>
          </div>
        ) : payload ? (
          <ErrorBoundary fallbackStep={() => setActiveStep(4)}>
            {activeStep === 1 && <Step1RawLake records={payload.records} />}
            {activeStep === 2 && (
              <Step2Blocking
                normalized={payload.normalized}
                candidatePairs={payload.candidate_pairs}
              />
            )}
            {activeStep === 3 && (
              <Step3Scoring
                scoredPairs={payload.all_pair_scores}
                threshold={threshold}
                onThresholdChange={setThreshold}
              />
            )}
            {activeStep === 4 && <Step4GraphVisualizer payload={payload} />}
            {activeStep === 5 && (
              <Step5GoldenMaster
                goldenEntities={payload.golden_entities}
                centrality={payload.centrality}
              />
            )}
            {activeStep === 6 && <Step6Benchmark benchmarks={payload.benchmark} />}
          </ErrorBoundary>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#21262d] bg-[#0d1117] px-6 py-3 text-xs text-slate-500 font-mono">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-2">
          <span>xMatch Studio POC &bull; Graph AI LLC</span>
          <div className="flex items-center gap-4">
            <span>GraphBLAS SuiteSparse Engine</span>
            <span>DuckDB 1.5.5 Vectorized Ingestion</span>
            <span className="text-blue-400">Target Integration: xGraph</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
