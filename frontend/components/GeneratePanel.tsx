"use client";

import { useCallback, useRef, useState } from "react";
import {
  cancelGenJob,
  createGenJob,
  getGenOutputUrl,
  streamGenProgress,
  uploadFace,
} from "@/lib/api";
import type { GenJob } from "@/types";
import { DropZone } from "./DropZone";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Loader2,
  RefreshCw,
  Server,
  Sparkles,
  XCircle,
} from "lucide-react";

type Stage = "idle" | "uploading" | "generating" | "done" | "error";
type ProviderMode = "hf" | "colab";

const PROMPT_SUGGESTIONS = [
  "Person walking slowly in a park, cinematic lighting",
  "Smiling and waving at camera, natural background",
  "Dancing gracefully, soft studio lighting",
  "Looking around curiously, bokeh background",
  "Gentle head turn, portrait style, golden hour",
];


export function GeneratePanel() {
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(5);

  // Provider configuration
  const [providerMode, setProviderMode] = useState<ProviderMode>("hf");

  const [stage, setStage] = useState<Stage>("idle");
  const [uploadMsg, setUploadMsg] = useState("");
  const [genJob, setGenJob] = useState<GenJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sseCleanupRef = useRef<(() => void) | null>(null);

  const handleImage = useCallback((file: File) => {
    setImageFile(file);
    setImagePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  }, []);

  const handleStart = useCallback(async () => {
    if (!imageFile || !prompt.trim()) return;

    setError(null);
    setStage("uploading");
    setUploadMsg("Image upload ho raha hai... 0%");

    try {
      const uploadResp = await uploadFace(imageFile, (pct) =>
        setUploadMsg(`Image upload ho raha hai... ${pct}%`)
      );

      setUploadMsg("Generation job create ho raha hai...");
      const job = await createGenJob({
        image_upload_id: uploadResp.path,
        prompt: prompt.trim(),
        duration,
        provider_mode: providerMode,
      });

      setGenJob(job);
      setStage("generating");

      const cleanup = streamGenProgress(
        job.job_id,
        (updated) => {
          setGenJob(updated);
          if (updated.status === "COMPLETED") setStage("done");
          else if (updated.status === "FAILED") {
            setStage("error");
            setError(updated.error_message || "Generation fail ho gayi.");
          } else if (updated.status === "CANCELLED") {
            setStage("idle");
          }
        },
        (err) => console.warn("SSE error:", err.message)
      );
      sseCleanupRef.current = cleanup;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setStage("error");
    }
  }, [imageFile, prompt, duration]);

  const handleCancel = useCallback(async () => {
    sseCleanupRef.current?.();
    if (genJob) {
      try { await cancelGenJob(genJob.job_id); } catch {}
    }
    setStage("idle");
    setGenJob(null);
    setError(null);
    setUploadMsg("");
  }, [genJob]);

  const handleReset = useCallback(() => {
    sseCleanupRef.current?.();
    setStage("idle");
    setImageFile(null);
    setImagePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setPrompt("");
    setDuration(5);
    setGenJob(null);
    setError(null);
    setUploadMsg("");
  }, []);

  const isRunning = stage === "uploading" || stage === "generating";
  const canStart = !!imageFile && prompt.trim().length > 0 && !isRunning;

  return (
    <motion.div
      className="space-y-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >

      {/* Provider Selector Card */}
      <motion.div
        className="rounded-2xl bg-slate-900 border border-slate-800 p-5 space-y-4"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-violet-400" />
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Execution Engine
            </span>
          </div>
          <span className="text-[11px] text-emerald-400 font-medium">
            Configured Securely via .env
          </span>
        </div>

        {/* Engine Tabs */}
        <div className="grid grid-cols-2 gap-3">
          {(["hf", "colab"] as ProviderMode[]).map((mode) => (
            <motion.button
              key={mode}
              type="button"
              onClick={() => setProviderMode(mode)}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              className={`flex flex-col p-3 rounded-xl border text-left transition-all ${
                providerMode === mode
                  ? "border-violet-500 bg-violet-950/40 text-white shadow-lg shadow-violet-500/10"
                  : "border-slate-800 bg-slate-850 text-slate-400 hover:border-slate-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-200">
                  {mode === "hf" ? "🤗 Hugging Face Cloud" : "🚀 Google Colab GPU"}
                </span>
                {providerMode === mode && (
                  <span className="text-[10px] text-violet-400 font-semibold">Active</span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                {mode === "hf" ? "Wan2.1 / CogVideoX / LTX" : "Free NVIDIA T4 (15GB VRAM)"}
              </p>
            </motion.button>
          ))}
        </div>

        {/* Status Hint */}
        <AnimatePresence mode="wait">
          <motion.p
            key={providerMode}
            className="text-[11px] text-slate-500 pt-1 border-t border-slate-800/80"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
          >
            {providerMode === "hf"
              ? "🔒 Hugging Face Token backend ke .env file se securely load hota hai."
              : "🚀 Colab Mode: Video Google ke free GPU (15GB VRAM) se render hoga (configured via .env)."}
          </motion.p>
        </AnimatePresence>
      </motion.div>

      {/* Main Generation Inputs */}
      <motion.div
        className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-5"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >

        {/* Image Upload */}
        <DropZone
          label="Apni Photo (Reference)"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          hint="JPG, PNG, WEBP — seedha, saaf photo"
          onFile={handleImage}
          preview={imagePreview}
          disabled={isRunning}
        />

        {/* Prompt */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Prompt — Kya karna chahte ho?
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={isRunning}
            placeholder="Person walking in a park, smiling, cinematic lighting..."
            rows={3}
            className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:border-violet-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          />
          {/* Suggestions */}
          <div className="flex flex-wrap gap-2">
            {PROMPT_SUGGESTIONS.map((s) => (
              <motion.button
                key={s}
                type="button"
                onClick={() => setPrompt(s)}
                disabled={isRunning}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                className="text-[11px] px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {s.length > 40 ? s.slice(0, 38) + "…" : s}
              </motion.button>
            ))}
          </div>
        </div>

        {/* Duration */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Duration
            </label>
            <motion.span
              key={duration}
              className="text-xs font-bold text-violet-400"
              initial={{ scale: 1.2, color: "#a78bfa" }}
              animate={{ scale: 1, color: "#8b5cf6" }}
              transition={{ duration: 0.2 }}
            >
              {duration} seconds
            </motion.span>
          </div>
          <input
            type="range"
            min={3}
            max={10}
            step={1}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
            disabled={isRunning}
            className="w-full h-1.5 bg-slate-700 rounded-full appearance-none cursor-pointer accent-violet-500 disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <div className="flex justify-between text-[10px] text-slate-600">
            <span>3s (fast)</span><span>6s</span><span>10s (slow)</span>
          </div>
        </div>

        {/* Error */}
        <AnimatePresence>
          {error && !isRunning && (
            <motion.div
              className="flex items-start gap-3 p-3 rounded-lg bg-red-950/50 border border-red-800"
              initial={{ opacity: 0, height: 0, y: -8 }}
              animate={{ opacity: 1, height: "auto", y: 0 }}
              exit={{ opacity: 0, height: 0 }}
            >
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{error}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action buttons */}
        <div className="flex gap-3">
          <AnimatePresence mode="wait">
            {stage === "idle" || stage === "error" ? (
              <motion.button
                key="start"
                type="button"
                onClick={handleStart}
                disabled={!canStart}
                whileHover={canStart ? { scale: 1.02 } : {}}
                whileTap={canStart ? { scale: 0.97 } : {}}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className={`flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm transition-all duration-200 ${
                  canStart
                    ? "bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/20"
                    : "bg-slate-800 text-slate-500 cursor-not-allowed"
                }`}
              >
                <Sparkles className="w-4 h-4" />
                Generate Video
              </motion.button>
            ) : isRunning ? (
              <motion.button
                key="cancel"
                type="button"
                onClick={handleCancel}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-red-700 hover:bg-red-600 text-white transition-colors"
              >
                <XCircle className="w-4 h-4" />
                Cancel
              </motion.button>
            ) : (
              <motion.button
                key="reset"
                type="button"
                onClick={handleReset}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Naya Generate Karo
              </motion.button>
            )}
          </AnimatePresence>
        </div>

        {/* Upload spinner */}
        <AnimatePresence>
          {stage === "uploading" && (
            <motion.div
              className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <Loader2 className="w-4 h-4 animate-spin text-violet-400 flex-shrink-0" />
              <span className="text-sm text-slate-400">{uploadMsg}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Progress / Output */}
      <AnimatePresence>
        {genJob && (stage === "generating" || stage === "done" || stage === "error") && (
          <motion.div
            className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Generation Status
            </h2>

            {/* Progress bar */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300">{genJob.stage_message}</span>
                <span className="text-xs font-bold text-violet-400">{genJob.progress}%</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    genJob.status === "FAILED"
                      ? "bg-red-500"
                      : genJob.status === "COMPLETED"
                      ? "bg-emerald-500"
                      : "bg-violet-500"
                  }`}
                  style={{ width: `${genJob.progress}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
              {genJob.provider && (
                <p className="text-[11px] text-slate-500">
                  Engine: <span className="text-slate-300 font-semibold">{genJob.provider}</span>
                </p>
              )}
            </div>

            {/* Output */}
            <AnimatePresence>
              {stage === "done" && genJob.output_ready && (
                <motion.div
                  className="space-y-3 pt-2 border-t border-slate-800"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-semibold text-emerald-300">Video ready hai!</span>
                  </div>
                  <video
                    src={getGenOutputUrl(genJob.job_id)}
                    controls
                    autoPlay
                    loop
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 max-h-64 object-contain"
                  />
                  <motion.a
                    href={getGenOutputUrl(genJob.job_id)}
                    download={`faceflux_gen_${genJob.job_id}.mp4`}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.97 }}
                    className="flex items-center justify-center gap-2 w-full py-2.5 px-5 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-semibold transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    Download Video
                  </motion.a>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Footer note */}
      <p className="text-center text-xs text-slate-600">
        Free AI Video Generation · Zero Cost · Secure &amp; Private
      </p>
    </motion.div>
  );
}

