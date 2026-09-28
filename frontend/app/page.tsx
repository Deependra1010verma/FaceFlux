"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelJob,
  createJob,
  fetchSystemInfo,
  streamJobProgress,
  uploadFace,
  uploadVideo,
} from "@/lib/api";
import type { FaceInfo, Job, JobProgress, Quality, SystemInfo } from "@/types";

import { DropZone } from "@/components/DropZone";
import { FaceGrid } from "@/components/FaceGrid";
import { GeneratePanel } from "@/components/GeneratePanel";
import { HardwareBadge } from "@/components/HardwareBadge";
import { ProgressBar } from "@/components/ProgressBar";
import { TryOnPanel } from "@/components/TryOnPanel";
import { VideoOutput } from "@/components/VideoOutput";
import { AlertCircle, Loader2, RefreshCw, Settings2, Sparkles, Wand2, XCircle } from "lucide-react";

type Stage = "idle" | "uploading" | "processing" | "done" | "error";
type Tab = "swap" | "generate" | "tryon";

export default function HomePage() {
  // ── Tab navigation ────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<Tab>("swap");

  // ── System info ─────────────────────────────────────────────────────────
  const [sysInfo, setSysInfo] = useState<SystemInfo | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendLoading, setBackendLoading] = useState(true);

  const loadSystemInfo = useCallback(() => {
    setBackendLoading(true);
    setBackendError(null);
    fetchSystemInfo()
      .then((info) => {
        setSysInfo(info);
      })
      .catch((e: Error) => setBackendError(e.message))
      .finally(() => setBackendLoading(false));
  }, []);

  useEffect(() => {
    loadSystemInfo();
  }, [loadSystemInfo]);

  // ── Files ────────────────────────────────────────────────────────────────
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [faceFiles, setFaceFiles] = useState<File[]>([]);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);
  const [facePreviews, setFacePreviews] = useState<string[]>([]);

  const handleVideoFile = useCallback((file: File) => {
    setVideoFile(file);
    if (file.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(file.name)) {
      setVideoPreview((prev) => {
        if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
        return URL.createObjectURL(file);
      });
    } else {
      setVideoPreview(file.name);
    }
  }, []);

  const handleClearVideo = useCallback(() => {
    setVideoFile(null);
    setVideoPreview((prev) => {
      if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
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

  // ── Settings ─────────────────────────────────────────────────────────────
  const [quality, setQuality] = useState<Quality>("balanced");
  const [enhance, setEnhance] = useState(false); // CodeFormer — enable after installing basicsr

  // ── Job state ─────────────────────────────────────────────────────────────
  const [stage, setStage] = useState<Stage>("idle");
  const [uploadProgress, setUploadProgress] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [selectedFaceIndex, setSelectedFaceIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const sseCleanupRef = useRef<(() => void) | null>(null);

  const detectedFaces: FaceInfo[] = job?.detected_faces ?? [];

  // ── Upload + start ────────────────────────────────────────────────────────
  const handleStart = useCallback(async () => {
    if (!videoFile || faceFiles.length === 0) {
      setError("Pehle video aur kam se kam ek face photo upload karo.");
      return;
    }

    setError(null);
    setStage("uploading");

    try {
      setUploadProgress("Video upload ho raha hai... 0%");
      const videoResp = await uploadVideo(videoFile, (pct) =>
        setUploadProgress(`Video upload ho raha hai... ${pct}%`)
      );

      // Upload all face reference photos
      const faceUploadPaths: string[] = [];
      for (let i = 0; i < faceFiles.length; i++) {
        const f = faceFiles[i];
        setUploadProgress(`Face photo ${i + 1}/${faceFiles.length} upload ho rahi hai... 0%`);
        const resp = await uploadFace(f, (pct) =>
          setUploadProgress(`Face photo ${i + 1}/${faceFiles.length} upload ho rahi hai... ${pct}%`)
        );
        faceUploadPaths.push(resp.path);
      }

      setUploadProgress("Video analyze ho raha hai, multi-angle faces fuse ho rahe hain...");
      const jobResp = await createJob({
        video_upload_id: videoResp.path,
        face_upload_ids: faceUploadPaths,
        target_face_index: selectedFaceIndex,
        quality,
        enhance,
      });

      setJob(jobResp);
      setStage("processing");

      // SSE progress stream
      const cleanup = streamJobProgress(
        jobResp.job_id,
        (p) => {
          setProgress(p);
          if (p.status === "COMPLETED") setStage("done");
          else if (p.status === "FAILED") {
            setStage("error");
            setError(p.error_message || "Processing fail ho gayi.");
          } else if (p.status === "CANCELLED") {
            setStage("idle");
            setJob(null);
            setProgress(null);
          }
        },
        () => {},
        (err) => {
          console.warn("SSE error, polling fallback:", err.message);
        }
      );
      sseCleanupRef.current = cleanup;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStage("error");
    }
  }, [videoFile, faceFiles, selectedFaceIndex, quality, enhance]);

  const handleReset = useCallback(() => {
    sseCleanupRef.current?.();
    setStage("idle");
    setVideoFile(null);
    setFaceFiles([]);
    setVideoPreview((prev) => {
      if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
      return null;
    });
    setFacePreviews((prev) => {
      prev.forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
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
      try {
        await cancelJob(job.job_id);
      } catch {
        // ignore — job may have already finished
      }
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
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">FaceFlux</h1>
              <p className="text-xs text-slate-400">Local AI Face Swap</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                backendLoading
                  ? "bg-yellow-400 animate-pulse"
                  : backendError
                  ? "bg-red-400"
                  : "bg-emerald-400 animate-pulse"
              }`}
            />
            <span className="text-xs text-slate-400">
              {backendLoading ? "Connecting..." : backendError ? "Backend offline" : "Local · Private"}
            </span>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-8 space-y-5">

        {/* ── Tab Navigation ── */}
        <div className="flex rounded-xl overflow-hidden border border-slate-700 bg-slate-900">
          {([
            { id: "swap" as Tab, label: "🎭 Face Swap", desc: "Face replace karo" },
            { id: "generate" as Tab, label: "✨ Generate", desc: "Photo → Video" },
            { id: "tryon" as Tab, label: "👕 Try-On", desc: "Clothes transfer" },
          ]).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-3 px-2 text-sm font-semibold transition-all ${
                activeTab === tab.id
                  ? "bg-violet-600 text-white"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <span>{tab.label}</span>
              <span className={`block text-[10px] font-normal mt-0.5 ${activeTab === tab.id ? "text-violet-200" : "text-slate-600"}`}>
                {tab.desc}
              </span>
            </button>
          ))}
        </div>

        {/* ── Backend Error ── */}
        {backendError && (
          <div className="p-4 rounded-xl bg-red-950/60 border border-red-800 space-y-3">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-300">Backend chal nahi raha</p>
                <p className="text-xs text-red-400 mt-1">{backendError}</p>
              </div>
            </div>
            <div className="bg-red-950/60 rounded-lg p-3 font-mono text-xs text-red-300 space-y-1">
              <p className="text-red-500 text-[11px] uppercase tracking-wide mb-2">Is terminal command se backend chalao:</p>
              <p>cd /home/deependra/Projects/FaceFlux/backend</p>
              <p>python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload</p>
            </div>
            <button
              onClick={loadSystemInfo}
              className="flex items-center gap-2 text-xs text-red-300 hover:text-red-200 transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              Dobara try karo
            </button>
          </div>
        )}

        {/* ── Hardware Badge ── */}
        {sysInfo && <HardwareBadge info={sysInfo} />}

        {/* ── Generate Tab ── */}
        {activeTab === "generate" && <GeneratePanel />}

        {/* ── Try-On Tab ── */}
        {activeTab === "tryon" && <TryOnPanel />}

        {/* ── Face Swap Tab ── */}
        {activeTab === "swap" && (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6 space-y-6">

          {/* Upload Zone */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <DropZone
              label="Target Media (Video ya Photo)"
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,image/jpeg,image/png,image/webp,.mp4,.mov,.mkv,.webm,.jpg,.jpeg,.png,.webp"
              hint="Video (MP4, MOV) ya Photo (JPG, PNG) — jisme face swap karna hai"
              onFile={handleVideoFile}
              preview={videoPreview}
              onClear={handleClearVideo}
              disabled={isProcessing}
            />
            <DropZone
              label="Tumhara Chehra (Reference Angles)"
              accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              hint="Multiple photos chuno (Front, Left, Right side angles)"
              multiple={true}
              onFiles={handleFaceFiles}
              previews={facePreviews}
              onRemovePreview={handleRemoveFace}
              disabled={isProcessing}
            />
          </div>

          {/* Face Selection — job create hone ke baad dikhega */}
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
                    <button
                      key={q}
                      onClick={() => setQuality(q)}
                      disabled={isProcessing}
                      className={`flex-1 py-2 text-xs font-semibold capitalize transition-colors ${
                        quality === q
                          ? "bg-violet-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-slate-300"
                      } disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-slate-600">
                  {quality === "fast" && "⚡ Jaldi — testing ke liye"}
                  {quality === "balanced" && "⚖️ Balanced — recommended"}
                  {quality === "high" && "✨ Best quality — slow"}
                </p>
              </div>

              {/* Enhancement Toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/60 border border-slate-700">
                <div>
                  <p className="text-xs font-semibold text-slate-300">Face Enhancement</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    CodeFormer — sharpens swapped face
                    {!enhance && <span className="text-amber-600 ml-1">(requires basicsr install)</span>}
                  </p>
                </div>
                <button
                  onClick={() => setEnhance((v) => !v)}
                  disabled={isProcessing}
                  className={`relative w-10 h-5 rounded-full transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                    enhance ? "bg-violet-600" : "bg-slate-600"
                  }`}
                  aria-label="Toggle face enhancement"
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${
                      enhance ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Error box */}
          {error && !isProcessing && (
            <div className="flex items-start gap-3 p-3 rounded-lg bg-red-950/50 border border-red-800">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3">
            {stage === "idle" || stage === "error" ? (
              <button
                onClick={handleStart}
                disabled={!canStart}
                className={`flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm transition-all duration-200
                  ${
                    canStart
                      ? "bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-500/20 hover:shadow-violet-500/30 active:scale-[0.98]"
                      : "bg-slate-800 text-slate-500 cursor-not-allowed"
                  }
                `}
              >
                <Wand2 className="w-4 h-4" />
                Start Face Swap
              </button>
            ) : stage === "processing" || stage === "uploading" ? (
              <button
                onClick={handleCancel}
                className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-red-700 hover:bg-red-600 text-white transition-colors active:scale-[0.98]"
              >
                <XCircle className="w-4 h-4" />
                Cancel
              </button>
            ) : (
              <button
                onClick={handleReset}
                className="flex items-center justify-center gap-2 flex-1 py-3 px-6 rounded-xl font-semibold text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Naya Start Karo
              </button>
            )}
          </div>

          {/* Upload spinner */}
          {stage === "uploading" && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 border border-slate-700">
              <Loader2 className="w-4 h-4 animate-spin text-violet-400 flex-shrink-0" />
              <span className="text-sm text-slate-400">{uploadProgress}</span>
            </div>
          )}
        </div>
        )}

        {/* ── Processing Section ── */}
        {activeTab === "swap" && (stage === "processing" || stage === "done" || stage === "error") && progress && (
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
              Processing Status
            </h2>
            <ProgressBar
              status={progress.status}
              progress={progress.progress}
              stageMessage={progress.stage_message}
              errorMessage={progress.error_message}
            />
          </div>
        )}

        {/* ── Output Section ── */}
        {activeTab === "swap" && stage === "done" && job && (
          <div className="rounded-2xl bg-slate-900 border border-slate-800 p-6">
            <VideoOutput
              jobId={job.job_id}
              isImage={
                videoFile
                  ? videoFile.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(videoFile.name)
                  : false
              }
            />
          </div>
        )}

        {/* ── Footer ── */}
        <footer className="text-center text-xs text-slate-700 pb-6 space-y-1">
          <p>FaceFlux · Local-only AI · No cloud · No tracking · No uploads</p>
          <p>InsightFace (non-commercial) · CodeFormer (Apache-2.0)</p>
        </footer>
      </div>
    </main>
  );
}
