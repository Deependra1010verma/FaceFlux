"use client";

import { useCallback, useState } from "react";
import { UploadCloud } from "lucide-react";

interface DropZoneProps {
  label: string;
  accept: string;
  hint: string;
  onFile: (file: File) => void;
  preview?: string | null;
  disabled?: boolean;
}

export function DropZone({
  label,
  accept,
  hint,
  onFile,
  preview,
  disabled,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) onFile(file);
    },
    [onFile, disabled]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onFile(file);
    },
    [onFile]
  );

  return (
    <div className="space-y-2">
      <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide">
        {label}
      </label>
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
        {preview ? (
          <div className="w-full h-full flex items-center justify-center p-3">
            {preview.startsWith("data:image") || preview.startsWith("blob:") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="preview"
                className="max-h-32 max-w-full rounded-lg object-contain"
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
          </div>
        ) : (
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
          type="file"
          accept={accept}
          onChange={handleChange}
          disabled={disabled}
          className="absolute inset-0 opacity-0 cursor-pointer"
        />
      </div>
    </div>
  );
}
