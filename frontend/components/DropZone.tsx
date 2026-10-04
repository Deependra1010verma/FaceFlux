"use client";

import { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import { Plus, UploadCloud, X, AlertTriangle, CheckCircle2 } from "lucide-react";

interface DropZoneProps {
  label: string;
  accept: string;
  hint: string;
  onFile?: (file: File) => void;
  onFiles?: (files: File[]) => void;
  preview?: string | null;
  previews?: string[];
  onRemovePreview?: (index: number) => void;
  onClear?: () => void;
  disabled?: boolean;
  multiple?: boolean;
}

/** Quick client-side image quality check — no library needed */
function checkImageQuality(file: File): Promise<{ ok: boolean; warning: string | null }> {
  return new Promise((resolve) => {
    if (!file.type.startsWith("image/")) {
      resolve({ ok: true, warning: null });
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      if (img.width < 128 || img.height < 128) {
        resolve({ ok: false, warning: "Image too small (min 128×128 px). Use a larger photo." });
      } else if (file.size < 5000) {
        resolve({ ok: false, warning: "File too small — may be corrupt or very low quality." });
      } else {
        resolve({ ok: true, warning: null });
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ ok: false, warning: "Could not read image. Try a different file." });
    };
    img.src = url;
  });
}

export function DropZone({
  label,
  accept,
  hint,
  onFile,
  onFiles,
  preview,
  previews,
  onRemovePreview,
  onClear,
  disabled,
  multiple = false,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [qualityWarning, setQualityWarning] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setQualityWarning(null);
      const { ok, warning } = await checkImageQuality(file);
      if (!ok && warning) {
        setQualityWarning(warning);
        return; // block bad files
      }
      if (warning) setQualityWarning(warning); // soft warning, still allow
      onFile?.(file);
    },
    [onFile]
  );

  const handleFiles = useCallback(
    async (files: File[]) => {
      setQualityWarning(null);
      const valid: File[] = [];
      for (const f of files) {
        const { ok, warning } = await checkImageQuality(f);
        if (ok) valid.push(f);
        else if (warning) setQualityWarning(warning);
      }
      if (valid.length > 0) onFiles?.(valid);
    },
    [onFiles]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      if (multiple && onFiles) {
        const fileList = Array.from(e.dataTransfer.files);
        if (fileList.length > 0) handleFiles(fileList);
      } else if (onFile) {
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }
    },
    [handleFile, handleFiles, disabled, multiple, onFile, onFiles]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (multiple && onFiles) {
        const fileList = Array.from(e.target.files || []);
        if (fileList.length > 0) {
          handleFiles(fileList);
          e.target.value = "";
        }
      } else if (onFile) {
        const file = e.target.files?.[0];
        if (file) {
          handleFile(file);
          e.target.value = "";
        }
      }
    },
    [handleFile, handleFiles, multiple, onFile, onFiles]
  );

  const hasMultiplePreviews = previews && previews.length > 0;
  const hasSinglePreview = !!preview;
  const hasAnyPreview = hasMultiplePreviews || hasSinglePreview;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
          {label}
        </label>
        {multiple && hasMultiplePreviews && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-violet-400 font-medium">
              {previews!.length} photo{previews!.length > 1 ? "s" : ""} selected
            </span>
            {!disabled && (
              <motion.button
                type="button"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => inputRef.current?.click()}
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-violet-600/30 hover:bg-violet-600/50 text-violet-300 border border-violet-500/40 transition-colors cursor-pointer"
              >
                <Plus className="w-3 h-3" />
                Add More
              </motion.button>
            )}
          </div>
        )}
      </div>

      {/* Quality Warning */}
      <AnimatePresence>
        {qualityWarning && (
          <motion.div
            initial={{ opacity: 0, y: -6, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -6, height: 0 }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-950/50 border border-amber-700/60 text-amber-300 text-xs"
          >
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            <span>{qualityWarning}</span>
            <button
              type="button"
              onClick={() => setQualityWarning(null)}
              className="ml-auto text-amber-400 hover:text-amber-200 cursor-pointer"
            >
              <X className="w-3 h-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        onDragOver={(e: React.DragEvent<HTMLDivElement>) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        animate={{
          borderColor: dragging ? "rgb(139 92 246)" : hasAnyPreview ? "rgb(100 116 139)" : "rgb(71 85 105)",
          backgroundColor: dragging ? "rgba(139,92,246,0.08)" : "rgba(30,41,59,0.5)",
          scale: dragging ? 1.01 : 1,
        }}
        transition={{ duration: 0.15 }}
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed min-h-[140px] cursor-pointer overflow-hidden
          ${disabled ? "opacity-50 cursor-not-allowed" : "hover:border-violet-500"}
        `}
      >
        {/* Multi-photo gallery */}
        {hasMultiplePreviews ? (
          <div className="w-full p-3 space-y-2.5 relative z-10">
            <div className="flex flex-wrap gap-2.5 justify-center items-center">
              <AnimatePresence>
                {previews!.map((url, idx) => (
                  <motion.div
                    key={url}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    className="relative group rounded-lg overflow-hidden border border-slate-700 bg-slate-900 shadow-md"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={url}
                      alt={`Face angle ${idx + 1}`}
                      className="w-16 h-16 object-cover"
                    />
                    <span className="absolute bottom-0 inset-x-0 bg-black/75 text-[9px] text-center text-slate-300 font-mono py-0.5">
                      Angle {idx + 1}
                    </span>
                    {onRemovePreview && !disabled && (
                      <motion.button
                        type="button"
                        whileHover={{ scale: 1.15 }}
                        whileTap={{ scale: 0.9 }}
                        title="Remove this photo"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          onRemovePreview(idx);
                        }}
                        className="absolute top-1 right-1 w-5 h-5 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg cursor-pointer z-20 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X className="w-3 h-3" />
                      </motion.button>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {/* Add More tile */}
              {!disabled && (
                <motion.button
                  type="button"
                  whileHover={{ scale: 1.05, borderColor: "rgb(139 92 246)" }}
                  whileTap={{ scale: 0.95 }}
                  onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }}
                  className="w-16 h-16 rounded-lg border-2 border-dashed border-violet-500/60 bg-violet-950/20 text-violet-300 flex flex-col items-center justify-center gap-1 cursor-pointer shadow-sm"
                >
                  <Plus className="w-5 h-5 text-violet-400" />
                  <span className="text-[9px] font-semibold text-violet-300">Add More</span>
                </motion.button>
              )}
            </div>
            <p className="text-center text-[11px] text-slate-400">
              💡 More angles = better 3D face fusion = sharper swap
            </p>
          </div>
        ) : hasSinglePreview ? (
          /* Single preview */
          <div className="w-full h-full flex items-center justify-center p-3 relative z-10">
            {preview!.startsWith("data:image") || preview!.startsWith("blob:") ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="relative"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preview!}
                  alt="preview"
                  className="max-h-32 max-w-full rounded-lg object-contain shadow"
                />
                <div className="absolute -top-1.5 -right-1.5">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 bg-slate-900 rounded-full" />
                </div>
              </motion.div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 rounded-full bg-violet-500/20 flex items-center justify-center">
                  <UploadCloud className="w-5 h-5 text-violet-400" />
                </div>
                <p className="text-sm text-slate-300 font-medium truncate max-w-[200px]">
                  {preview}
                </p>
              </div>
            )}
            {onClear && !disabled && (
              <motion.button
                type="button"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                title="Remove"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClear(); }}
                className="absolute top-2 right-2 w-6 h-6 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg cursor-pointer z-20"
              >
                <X className="w-3.5 h-3.5" />
              </motion.button>
            )}
          </div>
        ) : (
          /* Empty state */
          <motion.div
            className="flex flex-col items-center gap-3 p-6 text-center"
            animate={{ opacity: dragging ? 0.6 : 1 }}
          >
            <motion.div
              className="w-12 h-12 rounded-full bg-violet-500/10 flex items-center justify-center"
              animate={{ scale: dragging ? 1.15 : 1 }}
              transition={{ type: "spring", stiffness: 300 }}
            >
              <UploadCloud className="w-6 h-6 text-violet-400" />
            </motion.div>
            <div>
              <p className="text-sm text-slate-300">
                Drag & drop or{" "}
                <span className="text-violet-400 font-semibold">browse</span>
              </p>
              <p className="text-xs text-slate-500 mt-1">{hint}</p>
            </div>
          </motion.div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleChange}
          disabled={disabled}
          className="absolute inset-0 opacity-0 cursor-pointer"
        />
      </motion.div>
    </div>
  );
}
