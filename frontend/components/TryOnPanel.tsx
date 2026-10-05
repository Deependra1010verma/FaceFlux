"use client";

import { useCallback, useRef, useState } from "react";
import {
  cancelTryOnJob,
  createTryOnJob,
  getTryOnOutputUrl,
  streamTryOnProgress,
  uploadFace,
  uploadVideo,
} from "@/lib/api";
import type { TryOnJob } from "@/types";
import { DropZone } from "./DropZone";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Info,
  Loader2,
  RefreshCw,
  Shirt,
  XCircle,
} from "lucide-react";

type Stage = "idle" | "uploading" | "processing" | "done" | "error";


export function TryOnPanel() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);
  const [clothingFile, setClothingFile] = useState<File | null>(null);
  const [clothingPreview, setClothingPreview] = useState<string | null>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [uploadMsg, setUploadMsg] = useState("");
  const [tryOnJob, setTryOnJob] = useState<TryOnJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sseCleanupRef = useRef<(() => void) | null>(null);

  const handleVideo = useCallback((file: File) => {
    setVideoFile(file);
    setVideoPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  }, []);

  const handleClothing = useCallback((file: File) => {
    setClothingFile(file);
    setClothingPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  }, []);

  const handleStart = useCallback(async () => {
    if (!videoFile || !clothingFile) return;
    setError(null);
    setStage("uploading");

    try {
      setUploadMsg("Video upload ho raha hai... 0%");
      const videoResp = await uploadVideo(videoFile, (pct) =>
        setUploadMsg(`Video upload ho raha hai... ${pct}%`)
      );

      setUploadMsg("Clothing photo upload ho rahi hai... 0%");
      const clothingResp = await uploadFace(clothingFile, (pct) =>
        setUploadMsg(`Clothing photo upload ho rahi hai... ${pct}%`)
      );

      setUploadMsg("Try-on job start ho raha hai...");
      const job = await createTryOnJob({
        video_upload_id: videoResp.path,
        clothing_upload_id: clothingResp.path,
      });

      setTryOnJob(job);
      setStage("processing");

      const cleanup = streamTryOnProgress(
        job.job_id,
        (updated) => {
          setTryOnJob(updated);
          if (updated.status === "COMPLETED") setStage("done");
          else if (updated.status === "FAILED") {
            setStage("error");
            setError(updated.error_message || "Try-on fail ho gayi.");
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
  }, [videoFile, clothingFile]);

  const handleCancel = useCallback(async () => {
    sseCleanupRef.current?.();
    if (tryOnJob) {
      try { await cancelTryOnJob(tryOnJob.job_id); } catch {}
    }
    setStage("idle");
    setTryOnJob(null);
    setError(null);
    setUploadMsg("");
  }, [tryOnJob]);

  const handleReset = useCallback(() => {
    sseCleanupRef.current?.();
    setStage("idle");
    setVideoFile(null);
    setVideoPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setClothingFile(null);
    setClothingPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setTryOnJob(null);
    setError(null);
    setUploadMsg("");
  }, []);

  const isRunning = stage === "uploading" || stage === "processing";
  const canStart = !!videoFile && !!clothingFile && !isRunning;

  return (
    <motion.div
      className="space-y-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >

      {/* Info Banner */}
      <motion.div
        className="flex items-start gap-3 p-3 rounded-xl bg-violet-950/40 border border-violet-800/50"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <Shirt className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-violet-300 space-y-1">
          <p className="font-semibold">Virtual Try-On — Photo ke Clothes Video mein</p>
          <p className="text-violet-400">
            Ek video do + kisi photo ke clothes — AI woh clothes video mein transfer kar dega.
            Cloud pe process hoga, koi GPU nahi chahiye.
          </p>
        </div>
      </motion.div>

      {/* Warning about processing time */}
      <motion.div
        className="flex items-start gap-2 p-3 rounded-xl bg-amber-950/30 border border-amber-800/40"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <Info className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
        <p className="text-[11px] text-amber-400">
          <strong>Note:</strong> Yeh feature HuggingFace Spaces use karta hai jo kabhi busy hoti hain.
          Processing mein 5–20 min lag sakte hain. Short videos (under 15 sec) best results dete hain.
        </p>
      </motion.div>

      <motion.div
        className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-5"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >

        {/* Uploads */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <DropZone
            label="Source Video"
            accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
            hint="MP4, MOV — short video (under 15 sec recommended)"
            onFile={handleVideo}
            preview={videoPreview}
            disabled={isRunning}
          />
          <DropZone
            label="Clothing Reference Photo"
            accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
            hint="Jis insaan ke clothes chahiye uski full-body photo"
            onFile={handleClothing}
            preview={clothingPreview}
            disabled={isRunning}
          />
        </div>

        {/* Tips */}
        <div className="p-3 rounded-xl bg-slate-800/50 border border-slate-700 space-y-1.5">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Best Results Ke Liye</p>
          <ul className="text-[11px] text-slate-500 space-y-1 list-disc list-inside">
            <li>Video mein person seedha camera ki taraf ho</li>
            <li>Clothing photo mein full outfit clearly visible ho</li>
            <li>15 second se chhota video use karo</li>
            <li>Plain background videos pe better results milte hain</li>
          </ul>
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
                <Shirt className="w-4 h-4" />
                Try-On Start Karo
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
                Naya Try-On Karo
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

      {/* Progress */}
      <AnimatePresence>
        {tryOnJob && (stage === "processing" || stage === "done" || stage === "error") && (
          <motion.div
            className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
          >
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Try-On Status
            </h2>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300">{tryOnJob.stage_message}</span>
                <span className="text-xs font-bold text-violet-400">{tryOnJob.progress}%</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${
                    tryOnJob.status === "FAILED"
                      ? "bg-red-500"
                      : tryOnJob.status === "COMPLETED"
                      ? "bg-emerald-500"
                      : "bg-violet-500"
                  }`}
                  style={{ width: `${tryOnJob.progress}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                />
              </div>
              {tryOnJob.total_frames > 0 && (
                <p className="text-[11px] text-slate-500">
                  Frames: <span className="text-slate-300 font-semibold">{tryOnJob.processed_frames}</span> / {tryOnJob.total_frames} processed
                </p>
              )}
            </div>

            {/* Output */}
            <AnimatePresence>
              {stage === "done" && tryOnJob.output_ready && (
                <motion.div
                  className="space-y-3 pt-2 border-t border-slate-800"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-semibold text-emerald-300">Try-On video ready hai!</span>
                  </div>
                  <video
                    src={getTryOnOutputUrl(tryOnJob.job_id)}
                    controls
                    autoPlay
                    loop
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 max-h-64 object-contain"
                  />
                  <motion.a
                    href={getTryOnOutputUrl(tryOnJob.job_id)}
                    download={`faceflux_tryon_${tryOnJob.job_id}.mp4`}
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
      <p className="text-center text-xs text-slate-700">
        Powered by IDM-VTON · CatVTON · OOTDiffusion via HuggingFace Spaces · Free
      </p>
    </motion.div>
  );
}
