"use client";

import { JobStatus } from "@/types";
import { motion } from "@/lib/motion-shim";
import { CheckCircle2, XCircle, AlertCircle } from "lucide-react";

const STATUS_LABELS: Record<JobStatus, string> = {
  QUEUED: "Queued",
  ANALYZING: "Analyzing video...",
  DETECTING: "Detecting faces...",
  TRACKING: "Tracking target face...",
  SWAPPING: "Swapping faces...",
  ENHANCING: "Enhancing with GPEN...",
  ENCODING: "Encoding video...",
  COMPLETED: "Complete!",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

const STATUS_COLORS: Record<JobStatus, string> = {
  QUEUED: "bg-slate-500",
  ANALYZING: "bg-blue-500",
  DETECTING: "bg-indigo-500",
  TRACKING: "bg-violet-500",
  SWAPPING: "bg-purple-500",
  ENHANCING: "bg-fuchsia-500",
  ENCODING: "bg-pink-500",
  COMPLETED: "bg-emerald-500",
  FAILED: "bg-red-500",
  CANCELLED: "bg-slate-500",
};

// Step-by-step pipeline stages for visual timeline
const PIPELINE_STAGES: JobStatus[] = [
  "ANALYZING", "DETECTING", "SWAPPING", "ENHANCING", "ENCODING", "COMPLETED",
];

interface ProgressBarProps {
  status: JobStatus;
  progress: number;
  stageMessage: string;
  errorMessage?: string | null;
}

export function ProgressBar({ status, progress, stageMessage, errorMessage }: ProgressBarProps) {
  const barColor = STATUS_COLORS[status];
  const isFailed = status === "FAILED";
  const isComplete = status === "COMPLETED";
  const isActive = !isFailed && !isComplete && status !== "CANCELLED";

  // Which pipeline step are we on?
  const currentStepIdx = PIPELINE_STAGES.indexOf(status as JobStatus);

  return (
    <div className="space-y-4">
      {/* Pipeline step dots */}
      <div className="flex items-center gap-1.5">
        {PIPELINE_STAGES.map((stage, i) => {
          const isPast = currentStepIdx > i;
          const isCurrent = currentStepIdx === i;
          return (
            <div key={stage} className="flex items-center gap-1.5 flex-1">
              <div className="relative flex-shrink-0">
                <div
                  className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${
                    isPast
                      ? "bg-emerald-500"
                      : isCurrent
                      ? `${barColor} ring-2 ring-offset-1 ring-offset-slate-900 ring-violet-500/50`
                      : "bg-slate-700"
                  }`}
                />
                {isCurrent && isActive && (
                  <motion.div
                    className="absolute inset-0 rounded-full bg-violet-400/40"
                    animate={{ scale: [1, 1.8, 1], opacity: [0.8, 0, 0.8] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div className={`h-0.5 flex-1 rounded-full transition-colors duration-500 ${isPast ? "bg-emerald-500/60" : "bg-slate-700"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Status + percentage */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isFailed ? (
            <XCircle className="w-4 h-4 text-red-400" />
          ) : isComplete ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : (
            <motion.span
              className={`inline-block w-2 h-2 rounded-full ${barColor}`}
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            />
          )}
          <span className="text-sm font-medium text-slate-300">
            {STATUS_LABELS[status]}
          </span>
        </div>
        <span className="text-sm font-mono font-bold text-violet-400">{progress}%</span>
      </div>

      {/* Progress track — spring-animated fill */}
      <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${barColor} ${isActive ? "relative" : ""}`}
          animate={{ width: `${progress}%` }}
          transition={{ type: "spring", stiffness: 60, damping: 15 }}
        >
          {/* Shimmer effect when active */}
          {isActive && (
            <motion.div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent"
              animate={{ x: ["-100%", "200%"] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
            />
          )}
        </motion.div>
      </div>

      {/* Stage message */}
      <motion.p
        key={stageMessage}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-xs text-slate-500"
      >
        {stageMessage}
      </motion.p>

      {/* Error */}
      {isFailed && errorMessage && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="p-3 rounded-lg bg-red-950/50 border border-red-800"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-red-300 mb-1">Processing Failed</p>
              <p className="text-xs text-red-400 whitespace-pre-line">{errorMessage}</p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Success */}
      {isComplete && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 300 }}
          className="p-3 rounded-lg bg-emerald-950/50 border border-emerald-800"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <p className="text-sm text-emerald-300 font-medium">
              Processing complete! Scroll down to see your result.
            </p>
          </div>
        </motion.div>
      )}
    </div>
  );
}
