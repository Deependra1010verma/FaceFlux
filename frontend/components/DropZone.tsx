"use client";

import { useCallback, useRef, useState } from "react";
import { Plus, UploadCloud, X } from "lucide-react";

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
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;

      if (multiple && onFiles) {
        const fileList = Array.from(e.dataTransfer.files);
        if (fileList.length > 0) onFiles(fileList);
      } else if (onFile) {
        const file = e.dataTransfer.files[0];
        if (file) onFile(file);
      }
    },
    [onFile, onFiles, disabled, multiple]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (multiple && onFiles) {
        const fileList = Array.from(e.target.files || []);
        if (fileList.length > 0) {
          onFiles(fileList);
          e.target.value = "";
        }
      } else if (onFile) {
        const file = e.target.files?.[0];
        if (file) {
          onFile(file);
          e.target.value = "";
        }
      }
    },
    [onFile, onFiles, multiple]
  );

  const hasMultiplePreviews = previews && previews.length > 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide">
          {label}
        </label>
        {multiple && hasMultiplePreviews && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-violet-400 font-medium">
              {previews.length} photos selected
            </span>
            {!disabled && (
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-violet-600/30 hover:bg-violet-600/50 text-violet-300 border border-violet-500/40 transition-colors cursor-pointer"
              >
                <Plus className="w-3 h-3" />
                Add More
              </button>
            )}
          </div>
        )}
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-all duration-200 min-h-[140px] cursor-pointer
          ${dragging ? "border-violet-400 bg-violet-950/40" : "border-slate-600 bg-slate-800/50 hover:border-violet-500 hover:bg-slate-800"}
          ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        {/* Multi-Photo Gallery Preview */}
        {hasMultiplePreviews ? (
          <div className="w-full p-3 space-y-2.5 relative z-10">
            <div className="flex flex-wrap gap-2.5 justify-center items-center">
              {previews.map((url, idx) => (
                <div key={idx} className="relative group rounded-lg overflow-hidden border border-slate-700 bg-slate-900 shadow-md">
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
                    <button
                      type="button"
                      title="Is photo ko hatao"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onRemovePreview(idx);
                      }}
                      className="absolute top-1 right-1 w-5 h-5 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-110 active:scale-95 cursor-pointer z-20"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              ))}

              {/* Dedicated '+ Add More' Tile */}
              {!disabled && (
                <button
                  type="button"
                  title="Aur angles ya photos add karo"
                  onClick={(e) => {
                    e.stopPropagation();
                    inputRef.current?.click();
                  }}
                  className="w-16 h-16 rounded-lg border-2 border-dashed border-violet-500/60 bg-violet-950/20 hover:bg-violet-950/50 hover:border-violet-400 text-violet-300 flex flex-col items-center justify-center gap-1 transition-all cursor-pointer group shadow-sm active:scale-95"
                >
                  <Plus className="w-5 h-5 text-violet-400 group-hover:scale-125 transition-transform" />
                  <span className="text-[9px] font-semibold text-violet-300">Add More</span>
                </button>
              )}
            </div>
            <p className="text-center text-[11px] text-slate-400">
              💡 Har photo se different angle (front, left, right profile) milega
            </p>
          </div>
        ) : preview ? (
          /* Single Preview */
          <div className="w-full h-full flex items-center justify-center p-3 relative z-10">
            {preview.startsWith("data:image") || preview.startsWith("blob:") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="preview"
                className="max-h-32 max-w-full rounded-lg object-contain shadow"
              />
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
              <button
                type="button"
                title="Hatao"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onClear();
                }}
                className="absolute top-2 right-2 w-6 h-6 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-110 active:scale-95 cursor-pointer z-20"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        ) : (
          /* Default Empty State */
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            <div className="w-12 h-12 rounded-full bg-violet-500/10 flex items-center justify-center">
              <UploadCloud className="w-6 h-6 text-violet-400" />
            </div>
            <div>
              <p className="text-sm text-slate-300">
                Drag & drop or{" "}
                <span className="text-violet-400 font-semibold">browse</span>
              </p>
              <p className="text-xs text-slate-500 mt-1">{hint}</p>
            </div>
          </div>
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
      </div>
    </div>
  );
}
