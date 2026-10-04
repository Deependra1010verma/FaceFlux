"use client";

import { getOutputUrl } from "@/lib/api";
import { Copy, Download, SplitSquareHorizontal } from "lucide-react";
import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "@/lib/motion-shim";

/** Canvas-based side-by-side export — no library needed */
async function downloadSideBySide(
  beforeSrc: string,
  afterSrc: string,
  jobId: string
): Promise<void> {
  try {
    const [before, after] = await Promise.all([
      loadImage(beforeSrc),
      loadImage(afterSrc),
    ]);

    const w = Math.max(before.width, after.width);
    const h = Math.max(before.height, after.height);
    const padding = 4;
    const labelH = 28;

    const canvas = document.createElement("canvas");
    canvas.width = w * 2 + padding * 3;
    canvas.height = h + labelH + padding * 2;

    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw images
    ctx.drawImage(before, padding, padding, w, h);
    ctx.drawImage(after, w + padding * 2, padding, w, h);

    // Labels
    ctx.fillStyle = "rgba(0,0,0,0.7)";
    ctx.fillRect(padding, padding, 70, 24);
    ctx.fillRect(w + padding * 2, padding, 70, 24);

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 13px system-ui, sans-serif";
    ctx.fillText("BEFORE", padding + 8, padding + 16);
    ctx.fillText("AFTER", w + padding * 2 + 8, padding + 16);

    // Bottom label
    ctx.fillStyle = "#334155";
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillText(
      `FaceFlux · ${new Date().toLocaleString()}`,
      padding,
      h + padding * 2 + labelH - 8
    );

    // Download
    const link = document.createElement("a");
    link.href = canvas.toDataURL("image/jpeg", 0.92);
    link.download = `faceflux_comparison_${jobId}.jpg`;
    link.click();
  } catch (e) {
    console.warn("Side-by-side download failed:", e);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}


interface VideoOutputProps {
  jobId: string;
  isImage?: boolean;
  originalPreview?: string | null; // blob URL of original (for before/after)
}

/** Drag-based before/after comparison slider (no library needed — pure CSS/JS) */
function BeforeAfterSlider({
  beforeSrc,
  afterSrc,
}: {
  beforeSrc: string;
  afterSrc: string;
}) {
  const [position, setPosition] = useState(50); // 0–100
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const updatePosition = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    setPosition(pct);
  }, []);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragging.current = true;
      updatePosition(e.clientX);
      const onMove = (ev: MouseEvent) => {
        if (dragging.current) updatePosition(ev.clientX);
      };
      const onUp = () => {
        dragging.current = false;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [updatePosition]
  );

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      e.preventDefault();
      updatePosition(e.touches[0].clientX);
    },
    [updatePosition]
  );

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded-xl overflow-hidden bg-black select-none cursor-col-resize"
      style={{ aspectRatio: "16/9" }}
      onMouseDown={onMouseDown}
      onTouchMove={onTouchMove}
      onTouchStart={(e) => updatePosition(e.touches[0].clientX)}
    >
      {/* After (result) — full width base */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={afterSrc}
        alt="After (swapped)"
        className="absolute inset-0 w-full h-full object-contain"
        draggable={false}
      />

      {/* Before (original) — clipped to left of slider */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ width: `${position}%` }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={beforeSrc}
          alt="Before (original)"
          className="absolute inset-0 w-full h-full object-contain"
          style={{ minWidth: `${(100 / Math.max(position, 1)) * 100}%` }}
          draggable={false}
        />
      </div>

      {/* Slider line + handle */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-white shadow-xl"
        style={{ left: `${position}%` }}
      >
        {/* Handle */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-white shadow-2xl flex items-center justify-center border-2 border-slate-200">
          <SplitSquareHorizontal className="w-4 h-4 text-slate-700" />
        </div>
      </div>

      {/* Labels */}
      <div className="absolute top-2 left-3 text-[10px] font-bold text-white bg-black/60 px-2 py-0.5 rounded-full">
        BEFORE
      </div>
      <div className="absolute top-2 right-3 text-[10px] font-bold text-white bg-violet-600/80 px-2 py-0.5 rounded-full">
        AFTER
      </div>
    </div>
  );
}

export function VideoOutput({ jobId, isImage = false, originalPreview }: VideoOutputProps) {
  const outputUrl = getOutputUrl(jobId);
  const [isVideoError, setIsVideoError] = useState(false);
  const [viewMode, setViewMode] = useState<"result" | "compare">("result");

  const showImage = isImage || isVideoError;
  const canCompare = showImage && !!originalPreview;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2, type: "spring", stiffness: 300 }}
            className="w-2 h-2 rounded-full bg-emerald-400"
          />
          <label className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            Output Result
          </label>
        </div>
        <span className="text-[11px] text-emerald-400 font-medium">
          {showImage ? "✓ Photo ready" : "✓ Video ready"}
        </span>
      </div>

      {/* View mode tabs — only for images with original */}
      {canCompare && (
        <div className="flex rounded-lg overflow-hidden border border-slate-700 bg-slate-800 w-fit">
          {(["result", "compare"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
                viewMode === mode
                  ? "bg-violet-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {mode === "result" ? "Result" : "Before / After"}
            </button>
          ))}
        </div>
      )}

      {/* Media */}
      <AnimatePresence mode="wait">
        {viewMode === "compare" && canCompare ? (
          <motion.div
            key="compare"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <BeforeAfterSlider beforeSrc={originalPreview!} afterSrc={outputUrl} />
            <p className="text-center text-[11px] text-slate-500 mt-1.5">
              Drag slider to compare · Left = Original · Right = Swapped
            </p>
          </motion.div>
        ) : (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="relative rounded-xl overflow-hidden bg-black flex items-center justify-center border border-slate-800"
            style={{ aspectRatio: "16/9" }}
          >
            {showImage ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={outputUrl}
                alt="Face swap result"
                className="w-full h-full object-contain"
              />
            ) : (
              <video
                src={outputUrl}
                controls
                autoPlay
                loop
                className="w-full h-full object-contain"
                onError={() => setIsVideoError(true)}
              >
                Your browser does not support the video tag.
              </video>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Action Bar */}
      <div className="flex gap-2">
        {/* Primary: Download result */}
        <motion.a
          href={outputUrl}
          download={showImage ? `faceflux_swap_${jobId}.jpg` : `faceflux_${jobId}.mp4`}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          className="flex items-center justify-center gap-2 flex-1 py-3 px-4 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold text-sm transition-colors shadow-lg shadow-violet-600/20"
        >
          <Download className="w-4 h-4" />
          {showImage ? "Save Photo" : "Save Video"}
        </motion.a>

        {/* Secondary: Side-by-side download (images only) */}
        {canCompare && originalPreview && (
          <motion.button
            type="button"
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            data-tooltip="Download Before & After side-by-side"
            onClick={() => downloadSideBySide(originalPreview, outputUrl, jobId)}
            className="flex items-center justify-center gap-1.5 px-4 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium border border-slate-700 transition-colors cursor-pointer"
          >
            <SplitSquareHorizontal className="w-4 h-4" />
            <span className="hidden sm:inline">Side-by-Side</span>
          </motion.button>
        )}

        {/* Copy link */}
        <motion.button
          type="button"
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          data-tooltip="Copy download link"
          onClick={() => {
            navigator.clipboard.writeText(window.location.origin + outputUrl).catch(() => {});
          }}
          className="flex items-center justify-center gap-1.5 px-3 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 border border-slate-700 transition-colors cursor-pointer"
        >
          <Copy className="w-4 h-4" />
        </motion.button>
      </div>
    </motion.div>
  );
}
