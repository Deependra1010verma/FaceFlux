"use client";

/**
 * BatchPanel — Stage 5: Batch image processing
 *
 * Queue multiple target images to process with the same face reference.
 * Each image is processed sequentially (respects MAX_CONCURRENT_JOBS).
 * Results are downloadable as a zip-like sequential download.
 */

import { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  Layers,
  Loader2,
  Play,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { createJob, getOutputUrl, streamJobProgress, uploadFace, uploadVideo } from "@/lib/api";
import type { Quality } from "@/types";

interface BatchItem {
  id: string;
  file: File;
  previewUrl: string;
  status: "queued" | "uploading" | "processing" | "done" | "error";
  progress: number;
  jobId?: string;
  error?: string;
  outputUrl?: string;
}

interface BatchPanelProps {
  facePreviews: string[];
  faceFiles: File[];
  quality: Quality;
  enhance: boolean;
  disabled?: boolean;
}

export function BatchPanel({ facePreviews, faceFiles, quality, enhance, disabled }: BatchPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef(false);

  const addFiles = useCallback((files: FileList | null) => {
    if (!files) return;
    const newItems: BatchItem[] = Array.from(files)
      .filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(f.name))
      .map((f) => ({
        id: Math.random().toString(36).slice(2),
        file: f,
        previewUrl: URL.createObjectURL(f),
        status: "queued" as const,
        progress: 0,
      }));
    setItems((prev) => [...prev, ...newItems]);
  }, []);

  const removeItem = useCallback((id: string) => {
    setItems((prev) => {
      const item = prev.find((i) => i.id === id);
      if (item?.previewUrl) URL.revokeObjectURL(item.previewUrl);
      return prev.filter((i) => i.id !== id);
    });
  }, []);

  const clearAll = useCallback(() => {
    setItems((prev) => {
      prev.forEach((i) => { if (i.previewUrl) URL.revokeObjectURL(i.previewUrl); });
      return [];
    });
  }, []);

  const updateItem = useCallback((id: string, patch: Partial<BatchItem>) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  }, []);

  const runBatch = useCallback(async () => {
    if (faceFiles.length === 0) return;
    abortRef.current = false;
    setRunning(true);

    // Upload face references once (shared across all batch items)
    let faceUploadPaths: string[] = [];
    try {
      for (const f of faceFiles) {
        const resp = await uploadFace(f, () => {});
        faceUploadPaths.push(resp.path);
      }
    } catch {
      setRunning(false);
      return;
    }

    // Process each queued item sequentially
    for (const item of items) {
      if (abortRef.current) break;
      if (item.status !== "queued") continue;

      updateItem(item.id, { status: "uploading", progress: 5 });

      try {
        // Upload target image
        const videoResp = await uploadVideo(item.file, (pct) =>
          updateItem(item.id, { progress: Math.round(pct * 0.3) })
        );

        updateItem(item.id, { status: "processing", progress: 30 });

        // Create job
        const jobResp = await createJob({
          video_upload_id: videoResp.path,
          face_upload_ids: faceUploadPaths,
          target_face_index: 0,
          quality,
          enhance,
        });

        updateItem(item.id, { jobId: jobResp.job_id });

        // Wait for completion
        await new Promise<void>((resolve, reject) => {
          const cleanup = streamJobProgress(
            jobResp.job_id,
            (p) => {
              updateItem(item.id, { progress: 30 + Math.round(p.progress * 0.7) });
              if (p.status === "COMPLETED") {
                updateItem(item.id, {
                  status: "done",
                  progress: 100,
                  outputUrl: getOutputUrl(jobResp.job_id),
                });
                cleanup();
                resolve();
              } else if (p.status === "FAILED" || p.status === "CANCELLED") {
                updateItem(item.id, { status: "error", error: p.error_message || "Failed" });
                cleanup();
                reject(new Error(p.error_message || "Job failed"));
              }
            },
            () => {},
            (err) => {
              updateItem(item.id, { status: "error", error: err.message });
              reject(err);
            }
          );
        });
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        updateItem(item.id, { status: "error", error: msg, progress: 0 });
      }
    }

    setRunning(false);
  }, [faceFiles, items, quality, enhance, updateItem]);

  const stopBatch = useCallback(() => {
    abortRef.current = true;
    setRunning(false);
  }, []);

  const queuedCount = items.filter((i) => i.status === "queued").length;
  const doneCount = items.filter((i) => i.status === "done").length;

  if (!expanded) {
    return (
      <motion.button
        type="button"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={() => setExpanded(true)}
        className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-dashed border-slate-700 bg-slate-900/50 hover:border-slate-600 hover:bg-slate-800/50 transition-colors cursor-pointer group"
      >
        <div className="flex items-center gap-3">
          <Layers className="w-4 h-4 text-slate-500 group-hover:text-violet-400 transition-colors" />
          <div className="text-left">
            <p className="text-sm font-medium text-slate-400 group-hover:text-slate-300 transition-colors">
              Batch Mode
            </p>
            <p className="text-xs text-slate-600">
              Process multiple images with same face reference
            </p>
          </div>
        </div>
        <ChevronDown className="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors" />
      </motion.button>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className="rounded-xl border border-slate-700 bg-slate-900/80 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold text-slate-300">Batch Mode</span>
          {items.length > 0 && (
            <span className="text-[11px] bg-violet-950/60 text-violet-400 px-2 py-0.5 rounded-full border border-violet-800/40">
              {doneCount}/{items.length} done
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {items.length > 0 && !running && (
            <button
              type="button"
              onClick={clearAll}
              className="text-xs text-slate-500 hover:text-red-400 transition-colors flex items-center gap-1 cursor-pointer"
            >
              <Trash2 className="w-3 h-3" /> Clear
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
          >
            <ChevronUp className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Drop zone for batch files */}
        <label className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl border-2 border-dashed border-slate-700 hover:border-violet-500 hover:bg-violet-950/10 transition-colors cursor-pointer">
          <Layers className="w-6 h-6 text-slate-500" />
          <div className="text-center">
            <p className="text-sm text-slate-400">
              Drop images or <span className="text-violet-400 font-semibold">browse</span>
            </p>
            <p className="text-xs text-slate-600 mt-0.5">JPG, PNG, WEBP — unlimited files</p>
          </div>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
            multiple
            className="hidden"
            onChange={(e) => addFiles(e.target.files)}
            disabled={running || disabled}
          />
        </label>

        {/* Queue list */}
        {items.length > 0 && (
          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            <AnimatePresence>
              {items.map((item, idx) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ delay: idx * 0.03 }}
                  className="flex items-center gap-3 p-2 rounded-lg bg-slate-800/60 border border-slate-700/50"
                >
                  {/* Thumbnail */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={item.previewUrl}
                    alt={item.file.name}
                    className="w-10 h-10 rounded-md object-cover flex-shrink-0 border border-slate-700"
                  />

                  {/* Info + progress */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-300 truncate">{item.file.name}</p>
                    {item.status === "queued" && (
                      <p className="text-[11px] text-slate-600">Queued</p>
                    )}
                    {(item.status === "uploading" || item.status === "processing") && (
                      <div className="mt-1 h-1 bg-slate-700 rounded-full overflow-hidden">
                        <motion.div
                          className="h-full bg-violet-500 rounded-full"
                          animate={{ width: `${item.progress}%` }}
                          transition={{ type: "spring", stiffness: 80 }}
                        />
                      </div>
                    )}
                    {item.status === "error" && (
                      <p className="text-[11px] text-red-400 truncate">{item.error}</p>
                    )}
                  </div>

                  {/* Status icon */}
                  <div className="flex-shrink-0">
                    {item.status === "queued" && (
                      <div className="w-5 h-5 rounded-full border-2 border-slate-600" />
                    )}
                    {(item.status === "uploading" || item.status === "processing") && (
                      <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                    )}
                    {item.status === "done" && item.outputUrl && (
                      <a
                        href={item.outputUrl}
                        download={`faceflux_batch_${item.file.name}`}
                        className="text-emerald-400 hover:text-emerald-300 transition-colors"
                        data-tooltip="Download"
                      >
                        <Download className="w-4 h-4" />
                      </a>
                    )}
                    {item.status === "error" && (
                      <XCircle className="w-4 h-4 text-red-400" />
                    )}
                  </div>

                  {/* Remove */}
                  {!running && item.status !== "processing" && item.status !== "uploading" && (
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      className="text-slate-600 hover:text-slate-400 transition-colors cursor-pointer flex-shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* Warnings */}
        {faceFiles.length === 0 && (
          <p className="text-xs text-amber-400/80 bg-amber-950/30 border border-amber-800/40 rounded-lg px-3 py-2">
            ⚠ Upload face reference photos first (above) before starting batch.
          </p>
        )}

        {/* Action buttons */}
        <div className="flex gap-2">
          {!running ? (
            <motion.button
              type="button"
              whileHover={queuedCount > 0 && faceFiles.length > 0 ? { scale: 1.01 } : {}}
              whileTap={queuedCount > 0 && faceFiles.length > 0 ? { scale: 0.99 } : {}}
              onClick={runBatch}
              disabled={queuedCount === 0 || faceFiles.length === 0 || disabled}
              className={`flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                queuedCount > 0 && faceFiles.length > 0 && !disabled
                  ? "bg-violet-600 hover:bg-violet-500 text-white cursor-pointer"
                  : "bg-slate-800 text-slate-600 cursor-not-allowed"
              }`}
            >
              <Play className="w-4 h-4" />
              {queuedCount > 0
                ? `Process ${queuedCount} Image${queuedCount > 1 ? "s" : ""}`
                : "Add Images to Queue"}
            </motion.button>
          ) : (
            <motion.button
              type="button"
              whileTap={{ scale: 0.98 }}
              onClick={stopBatch}
              className="flex items-center justify-center gap-2 flex-1 py-2.5 rounded-xl text-sm font-semibold bg-red-700 hover:bg-red-600 text-white transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
              Stop Batch
            </motion.button>
          )}

          {doneCount > 0 && !running && (
            <button
              type="button"
              onClick={() => {
                // Download all completed results sequentially
                items
                  .filter((i) => i.status === "done" && i.outputUrl)
                  .forEach((i, idx) => {
                    setTimeout(() => {
                      const a = document.createElement("a");
                      a.href = i.outputUrl!;
                      a.download = `faceflux_batch_${idx + 1}_${i.file.name}`;
                      a.click();
                    }, idx * 500);
                  });
              }}
              className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium bg-emerald-800/60 hover:bg-emerald-800/80 text-emerald-300 border border-emerald-800/40 transition-colors cursor-pointer"
            >
              <Download className="w-4 h-4" />
              All ({doneCount})
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
