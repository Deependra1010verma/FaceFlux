"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import {
  cancelJob,
  createJob,
  fetchSystemInfo,
  setApiBaseUrl,
  streamJobProgress,
  uploadFace,
  uploadVideo,
} from "@/lib/api";
import type { FaceInfo, Job, JobProgress, Quality, SystemInfo } from "@/types";

import { DropZone } from "@/components/DropZone";
import { BatchPanel } from "@/components/BatchPanel";
import { FaceGrid } from "@/components/FaceGrid";
import { GeneratePanel } from "@/components/GeneratePanel";
import { HardwareBadge } from "@/components/HardwareBadge";
import { ProgressBar } from "@/components/ProgressBar";
import { ServerModal } from "@/components/ServerModal";
import { TryOnPanel } from "@/components/TryOnPanel";
import { VideoOutput } from "@/components/VideoOutput";
import {
  AlertCircle,
  Clock,
  Loader2,
  RefreshCw,
  Settings2,
  Sparkles,
  Trash2,
  Wand2,
  XCircle,
  Zap,
} from "lucide-react";

type Stage = "idle" | "uploading" | "processing" | "done" | "error";
type Tab = "swap" | "generate" | "tryon";

interface HistoryEntry {
  jobId: string;
  timestamp: number;
  isImage: boolean;
  previewUrl?: string; // thumbnail of result
}

// ── Local history (localStorage) ────────────────────────────────────────────
const HISTORY_KEY = "faceflux_history";
function loadHistory(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}
function saveHistory(entries: HistoryEntry[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, 10)));
  } catch {}
}

export default function HomePage() {
  // ── Tab ──────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>("swap");

  // ── System info ──────────────────────────────────────────────────────────
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendLoading, setBackendLoading] = useState(true);
  const [showServerModal, setShowServerModal] = useState(false);

  const loadSystemInfo = useCallback(() => {
    setBackendLoading(true);
    setBackendError(null);
    fetchSystemInfo()
      .then((info) => setSysInfo(info))
      .catch((e: Error) => setBackendError(e.message))
      .finally(() => setBackendLoading(false));
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const serverParam = params.get("server");
      if (serverParam?.trim()) {
        setApiBaseUrl(serverParam.trim());
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }
    loadSystemInfo();
  }, [loadSystemInfo]);

  // ── Files ─────────────────────────────────────────────────────────────────
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [faceFiles, setFaceFiles] = useState<File[]>([]);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);
  const [facePreviews, setFacePreviews] = useState<string[]>([]);

  const handleVideoFile = useCallback((file: File) => {
    setVideoFile(file);
    if (file.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(file.name)) {
      setVideoPreview((prev) => {
        if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
        return URL.createObjectURL(file);
      });
    } else {
      setVideoPreview(file.name);
    }
  }, []);

  const handleClearVideo = useCallback(() => {
    setVideoFile(null);
    setVideoPreview((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  const handleFaceFiles = useCallback((newFiles: File[]) => {
    setFaceFiles((prev) => [...prev, ...newFiles]);
    const newUrls = newFiles.map((f) => URL.createObjectURL(f));
    setFacePreviews((prev) => [...prev, ...newUrls]);
  }, []);

  const handleRemoveFace = useCallback((index: number) => {
    setFaceFiles((prev) => prev.filter((_, i) => i !== index));
    setFacePreviews((prev) => {
      const urlToRemove = prev[index];
      if (urlToRemove) URL.revokeObjectURL(urlToRemove);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  // ── Settings ──────────────────────────────────────────────────────────────
  const [quality, setQuality] = useState<Quality>("balanced");
  const [enhance, setEnhance] = useState(true); // GPEN ONNX — always enabled now

  // ── Job state ─────────────────────────────────────────────────────────────
  const [stage, setStage] = useState<Stage>("idle");
  const [uploadProgress, setUploadProgress] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [selectedFaceIndex, setSelectedFaceIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const sseCleanupRef = useRef<(() => void) | null>(null);

  // ── History ───────────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setHistory(loadHistory());
    }
  }, []);

  const addToHistory = useCallback((jobId: string, isImage: boolean) => {
    const entry: HistoryEntry = { jobId, timestamp: Date.now(), isImage };
    setHistory((prev) => {
      const updated = [entry, ...prev.slice(0, 9)];
      saveHistory(updated);
      return updated;
    });
  }, []);

  const detectedFaces: FaceInfo[] = job?.detected_faces ?? [];

  // ── Is the current target an image? ──────────────────────────────────────
  const targetIsImage =
    !!videoFile &&
    (videoFile.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(videoFile.name));

  // ── Upload + start ────────────────────────────────────────────────────────
  const handleStart = useCallback(async () => {
    if (!videoFile || faceFiles.length === 0) {
      setError("Please upload a target media file and at least one face reference photo.");
      return;
    }

    setError(null);
    setStage("uploading");

    try {
      setUploadProgress("Uploading video... 0%");
      const videoResp = await uploadVideo(videoFile, (pct) =>
        setUploadProgress(`Uploading video... ${pct}%`)
      );

      const faceUploadPaths: string[] = [];
      for (let i = 0; i < faceFiles.length; i++) {
        const f = faceFiles[i];
        setUploadProgress(`Uploading face photo ${i + 1}/${faceFiles.length}... 0%`);
        const resp = await uploadFace(f, (pct) =>
          setUploadProgress(`Uploading face photo ${i + 1}/${faceFiles.length}... ${pct}%`)
        );
        faceUploadPaths.push(resp.path);
      }

      setUploadProgress("Analyzing video & fusing multi-angle face...");
      const jobResp = await createJob({
        video_upload_id: videoResp.path,
        face_upload_ids: faceUploadPaths,
        target_face_index: selectedFaceIndex,
        quality,
        enhance,
      });

      setJob(jobResp);
      setStage("processing");

      const cleanup = streamJobProgress(
        jobResp.job_id,
        (p) => {
          setProgress(p);
          if (p.status === "COMPLETED") {
            setStage("done");
            addToHistory(jobResp.job_id, targetIsImage);
          } else if (p.status === "FAILED") {
            setStage("error");
            setError(p.error_message || "Processing failed.");
          } else if (p.status === "CANCELLED") {
            setStage("idle");
            setJob(null);
            setProgress(null);
          }
        },
        () => {},
        (err) => console.warn("SSE error, polling fallback:", err.message)
      );
      sseCleanupRef.current = cleanup;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStage("error");
    }
  }, [videoFile, faceFiles, selectedFaceIndex, quality, enhance, targetIsImage, addToHistory]);

  const handleReset = useCallback(() => {
    sseCleanupRef.current?.();
    setStage("idle");
    setVideoFile(null);
    setFaceFiles([]);
    setVideoPreview((prev) => {
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
    setFacePreviews((prev) => {
      prev.forEach((url) => url && URL.revokeObjectURL(url));
      return [];
    });
    setJob(null);
    setProgress(null);
    setError(null);
    setSelectedFaceIndex(0);
    setUploadProgress("");
  }, []);

  const handleCancel = useCallback(async () => {
    sseCleanupRef.current?.();
    if (job) {
      try { await cancelJob(job.job_id); } catch {}
    }
    setStage("idle");
    setJob(null);
    setProgress(null);
    setError(null);
    setSelectedFaceIndex(0);
    setUploadProgress("");
  }, [job]);

  const isProcessing = stage === "processing" || stage === "uploading";
  const canStart = !!videoFile && faceFiles.length > 0 && stage === "idle" && !backendError;

  return (
    <main className="min-h-screen bg-slate-950 text-white">

      {/* ── Header ── */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <motion.div
              whileHover={{ rotate: 15, scale: 1.1 }}
              transition={{ type: "spring", stiffness: 300 }}
              className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-600/30"
            >
              <Sparkles className="w-4 h-4 text-white" />
            </motion.div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">FaceFlux</h1>
              <p className="text-xs text-slate-400">Local AI · Private · No Cloud</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* History button */}
            {history.length > 0 && (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setShowHistory((v) => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700/80 transition text-xs font-medium text-slate-300"
              >
                <Clock className="w-3.5 h-3.5" />
                History
              </motion.button>
            )}

            {/* Server status */}
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => setShowServerModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700/80 transition text-xs font-medium text-slate-300"
            >
              <div
                className={`w-2 h-2 rounded-full ${
                  backendLoading
                    ? "bg-yellow-400 animate-pulse"
                    : backendError
                    ? "bg-red-400"
                    : "bg-emerald-400 animate-pulse"
                }`}
              />
              <span>
                {backendLoading ? "Connecting..." : backendError ? "Offline" : "Connected"}
              </span>
              <Settings2 className="w-3.5 h-3.5 text-slate-400 ml-0.5" />
            </motion.button>
          </div>
        </div>
      </header>

      <ServerModal
        isOpen={showServerModal}
        onClose={() => setShowServerModal(false)}
        onServerChange={() => loadSystemInfo()}
      />

      <div className="max-w-4xl mx-auto px-4 py-8 space-y-5">

        {/* ── History Panel ── */}
        <AnimatePresence>
          {showHistory && history.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="rounded-2xl bg-slate-900 border border-slate-800 p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Recent Swaps
                </span>
                <button
                  onClick={() => { setHistory([]); saveHistory([]); setShowHistory(false); }}
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-red-400 transition-colors cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" />
                  Clear
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {history.map((entry) => (
                  <motion.a
                    key={entry.jobId}
                    whileHover={{ scale: 1.05 }}
                    href={`/api/jobs/${entry.jobId}/output`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 w-16 h-16 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-500 hover:border-violet-500 transition-colors overflow-hidden"
                    title={`Job ${entry.jobId.slice(0, 8)}... — ${new Date(entry.timestamp).toLocaleTimeString()}`}
                  >
                    <span className="text-center px-1">
                      {entry.isImage ? "📷" : "🎬"}
                      <br />
                      {new Date(entry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </motion.a>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Tab Navigation ── */}
        <div className="flex rounded-xl overflow-hidden border border-slate-700 bg-slate-900">
          {(
            [
              { id: "swap" as Tab, label: "🎭 Face Swap", desc: "Replace any face" },
              { id: "generate" as Tab, label: "✨ Generate", desc: "Photo → Video" },
              { id: "tryon" as Tab, label: "👕 Try-On", desc: "Clothes transfer" },
            ] as const
          ).map((tab) => (
            <motion.button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              whileTap={{ scale: 0.97 }}
              className={`flex-1 py-3 px-2 text-sm font-semibold transition-all relative ${
                activeTab === tab.id
                  ? "text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {activeTab === tab.id && (
                <motion.div
                  layoutId="activeTab"
                  className="absolute inset-0 bg-violet-600"
                  style={{ zIndex: -1 }}
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <span className="relative z-10">{tab.label}</span>
              <span
                className={`relative z-10 block text-[10px] font-normal mt-0.5 ${
                  activeTab === tab.id ? "text-violet-200" : "text-slate-600"
                }`}
              >
                {tab.desc}
              </span>
            </motion.button>
          ))}
        </div>

        {/* ── Backend Error ── */}
        <AnimatePresence>
          {backendError && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="p-4 rounded-xl bg-red-950/60 border border-red-800 space-y-3"
            >
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-300">Backend not running</p>
                  <p className="text-xs text-red-400 mt-1">{backendError}</p>
                </div>
              </div>
              <div className="bg-red-950/60 rounded-lg p-3 font-mono text-xs text-red-300 space-y-1">
                <p className="text-red-500 text-[11px] uppercase tracking-wide mb-2">Start backend:</p>
                <p>cd /home/deependra/Projects/FaceFlux/backend</p>
                <p>python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload</p>
              </div>
              <div className="flex items-center gap-4 pt-1">
                <button
                  onClick={loadSystemInfo}
                  className="flex items-center gap-2 text-xs text-red-300 hover:text-red-200 transition-colors font-medium cursor-pointer"
                >
                  <RefreshCw className="w-3 h-3" />
                  Retry
                </button>
                <button
                  onClick={() => setShowServerModal(true)}
                  className="flex items-center gap-1.5 text-xs text-violet-300 hover:text-violet-200 transition-colors font-medium underline cursor-pointer"
                >
                  <Settings2 className="w-3 h-3" />
                  Change Server URL
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Hardware Badge ── */}
        {sysInfo && <HardwareBadge info={sysInfo} />}

        {/* ── Generate Tab ── */}
        {activeTab === "generate" && <GeneratePanel />}

        {/* ── Try-On Tab ── */}
        {activeTab === "tryon" && <TryOnPanel />}

        {/* ── Face Swap Tab ── */}
        <AnimatePresence mode="wait">
          {activeTab === "swap" && (
            <motion.div
              key="swap"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25 }}
              className="space-y-5"
            >
              <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-6">

                {/* Upload Zone */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <DropZone
                    label="Target Media (Video or Photo)"
                    accept="video/mp4,video/quicktime,video/x-matroska,video/webm,image/jpeg,image/png,image/webp,.mp4,.mov,.mkv,.webm,.jpg,.jpeg,.png,.webp"
                    hint="Video (MP4, MOV) or Photo (JPG, PNG) — the face to replace"
                    onFile={handleVideoFile}
                    preview={videoPreview}
                    onClear={handleClearVideo}
                    disabled={isProcessing}
                  />
                  <DropZone
                    label="Your Face (Reference Photos)"
                    accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                    hint="Add multiple angles (front, left, right) for best quality"
                    multiple={true}
                    onFiles={handleFaceFiles}
                    previews={facePreviews}
                    onRemovePreview={handleRemoveFace}
                    disabled={isProcessing}
                  />
                </div>

                {/* Face Selection */}
                {detectedFaces.length > 0 && (
                  <FaceGrid
                    faces={detectedFaces}
                    selectedIndex={selectedFaceIndex}
                    onSelect={setSelectedFaceIndex}
                  />
                )}

                {/* Settings */}
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Settings2 className="w-4 h-4 text-slate-500" />
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Settings
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    {/* Quality Mode */}
                    <div className="space-y-1.5">
                      <label className="text-xs text-slate-500">Quality Mode</label>
                      <div className="flex rounded-lg overflow-hidden border border-slate-700">
                        {(["fast", "balanced", "high"] as Quality[]).map((q) => (
                          <motion.button
                            key={q}
                            whileTap={{ scale: 0.97 }}
                            onClick={() => setQuality(q)}
                            disabled={isProcessing}
                            className={`flex-1 py-2 text-xs font-semibold capitalize transition-colors ${
                              quality === q
                                ? "bg-violet-600 text-white"
                                : "bg-slate-800 text-slate-400 hover:text-slate-300"
                            } disabled:opacity-50 disabled:cursor-not-allowed`}
                          >
                            {q}
                          </motion.button>
                        ))}
                      </div>
                      <p className="text-[11px] text-slate-600">
                        {quality === "fast" && "⚡ Fast — good for testing"}
                        {quality === "balanced" && "⚖️ Balanced — recommended"}
                        {quality === "high" && "✨ Best quality — slower"}
                      </p>
                    </div>

                    {/* GPEN Enhancement Toggle */}
                    <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/60 border border-slate-700">
                      <div>
                        <p className="text-xs font-semibold text-slate-300">GPEN Face Enhancement</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Sharpens swapped face · 128px → 512px quality · Pure ONNX
                        </p>
                      </div>
                      <motion.button
                        whileTap={{ scale: 0.9 }}
                        onClick={() => setEnhance((v) => !v)}
                        disabled={isProcessing}
                        className={`relative w-10 h-5 rounded-full transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
                          enhance ? "bg-violet-600" : "bg-slate-600"
                        }`}
                        aria-label="Toggle GPEN face enhancement"
                      >
                        <motion.span
                          animate={{ x: enhance ? 20 : 2 }}
                          transition={{ type: "spring", stiffness: 300, damping: 25 }}
                          className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow"
                        />
                      </motion.button>
                    </div>
                  </div>
                </div>

                {/* Error box */}
                <AnimatePresence>
                  {error && !isProcessing && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="flex items-start gap-3 p-3 rounded-lg bg-red-950/50 border border-red-800"
                    >
                      <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-red-300 whitespace-pre-line">{error}</p>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Action Buttons */}
                <div className="flex gap-3">
                  {stage === "idle" || stage === "error" ? (
                    <motion.button
                      onClick={handleStart}
                      disabled={!canStart}
                      whileHover={canStart ? { scale: 1.01 } : {}}
                      whileTap={canStart ? { scale: 0.98 } : {}}
                      className={`flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm transition-all duration-200 ${
                        canStart
                          ? "bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/20 hover:shadow-violet-500/30"
                          : "bg-slate-800 text-slate-500 cursor-not-allowed"
                      }`}
                    >
                      <Wand2 className="w-4 h-4" />
                      Start Face Swap
                    </motion.button>
                  ) : stage === "processing" || stage === "uploading" ? (
                    <motion.button
                      onClick={handleCancel}
                      whileTap={{ scale: 0.98 }}
                      className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-red-700 hover:bg-red-600 text-white transition-colors cursor-pointer"
                    >
                      <XCircle className="w-4 h-4" />
                      Cancel
                    </motion.button>
                  ) : (
                    <motion.button
                      onClick={handleReset}
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.98 }}
                      className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors cursor-pointer"
                    >
                      <RefreshCw className="w-4 h-4" />
                      New Swap
                    </motion.button>
                  )}
                </div>

                {/* Upload progress */}
                <AnimatePresence>
                  {stage === "uploading" && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700"
                    >
                      <Loader2 className="w-4 h-4 animate-spin text-violet-400 flex-shrink-0" />
                      <span className="text-sm text-slate-400">{uploadProgress}</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* ── Batch Mode ── */}
              <BatchPanel
                facePreviews={facePreviews}
                faceFiles={faceFiles}
                quality={quality}
                enhance={enhance}
                disabled={isProcessing}
              />

              {/* ── Processing Status ── */}
              <AnimatePresence>
                {(stage === "processing" || stage === "done" || stage === "error") && progress && (
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -12 }}
                    className="rounded-2xl bg-slate-900 border border-slate-800 p-6"
                  >
                    <div className="flex items-center gap-2 mb-4">
                      <Zap className="w-4 h-4 text-violet-400" />
                      <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                        Processing Status
                      </h2>
                    </div>
                    <ProgressBar
                      status={progress.status}
                      progress={progress.progress}
                      stageMessage={progress.stage_message}
                      errorMessage={progress.error_message}
                    />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* ── Output ── */}
              <AnimatePresence>
                {stage === "done" && job && (
                  <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="rounded-2xl bg-slate-900 border border-slate-800 p-6"
                  >
                    <VideoOutput
                      jobId={job.job_id}
                      isImage={targetIsImage}
                      originalPreview={targetIsImage && videoPreview?.startsWith("blob:") ? videoPreview : null}
                    />
                  </motion.div>
                )}
              </AnimatePresence>

            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Footer ── */}
        <footer className="text-center text-xs text-slate-700 pb-6 space-y-1">
          <p>FaceFlux v2.0 · Local-only AI · No cloud · No tracking</p>
          <p>InsightFace (non-commercial) · GPEN (MIT) · Color correction built-in</p>
        </footer>
      </div>
    </main>
  );
}
