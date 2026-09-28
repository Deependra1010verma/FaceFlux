"use client";

import { JobStatus } from "@/types";

const STATUS_LABELS: Record<JobStatus, string> = {
  QUEUED: "Queued",
  ANALYZING: "Analyzing video...",
  DETECTING: "Detecting faces...",
  TRACKING: "Tracking target face...",
  SWAPPING: "Swapping faces...",
  ENHANCING: "Enhancing...",
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

interface ProgressBarProps {
  status: JobStatus;
  progress: number;
  stageMessage: string;
  errorMessage?: string | null;
}

export function ProgressBar({
  status,
  progress,
  stageMessage,
  errorMessage,
}: ProgressBarProps) {
  const barColor = STATUS_COLORS[status];
  const isFailed = status === "FAILED";
  const isComplete = status === "COMPLETED";

  return (
    <div className="space-y-3">
      {/* Status badge + message */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${barColor} ${
              !isComplete && !isFailed ? "animate-pulse" : ""
            }`}
          />
          <span className="text-sm font-medium text-slate-300">
            {STATUS_LABELS[status]}
          </span>
        </div>
        <span className="text-sm font-mono text-slate-400">{progress}%</span>
      </div>

      {/* Progress track */}
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor} ${
            !isComplete && !isFailed ? "animate-pulse-subtle" : ""
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Stage message */}
      <p className="text-xs text-slate-500">{stageMessage}</p>

      {/* Error */}
      {isFailed && errorMessage && (
        <div className="mt-2 p-3 rounded-lg bg-red-950/50 border border-red-800 text-sm text-red-300">
          <strong>Error:</strong> {errorMessage}
        </div>
      )}

      {/* Success */}
      {isComplete && (
        <div className="mt-2 p-3 rounded-lg bg-emerald-950/50 border border-emerald-800 text-sm text-emerald-300">
          ✓ Processing complete! Your output video is ready.
        </div>
      )}
    </div>
  );
}
