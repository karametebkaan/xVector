import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackStep?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error in component:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="bg-[#161b22] border border-red-800/80 p-6 rounded-2xl max-w-2xl mx-auto my-12 text-center space-y-4 shadow-xl">
          <div className="w-12 h-12 bg-red-950/80 border border-red-500/50 rounded-full flex items-center justify-center mx-auto text-red-400">
            <AlertTriangle size={24} />
          </div>
          <h3 className="text-lg font-bold text-white tracking-tight">Component Rendering Error</h3>
          <p className="text-xs text-red-300 font-mono bg-red-950/40 p-3 rounded-lg border border-red-900/40 text-left overflow-x-auto">
            {this.state.error?.message || "Unknown error occurred during rendering."}
          </p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                if (this.props.fallbackStep) this.props.fallbackStep();
              }}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-xs px-4 py-2 rounded-lg font-medium transition"
            >
              <RefreshCw size={14} /> Reset View
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
