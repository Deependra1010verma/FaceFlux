"use client";

import { FaceInfo } from "@/types";

interface FaceGridProps {
  faces: FaceInfo[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export function FaceGrid({ faces, selectedIndex, onSelect }: FaceGridProps) {
  if (faces.length === 0) return null;

  return (
    <div className="space-y-3">
      <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide">
        Detected Faces — Select Target
      </label>
      <div className="flex flex-wrap gap-3">
        {faces.map((face) => (
          <button
            key={face.index}
            onClick={() => onSelect(face.index)}
            className={`relative flex flex-col items-center gap-1.5 p-2 rounded-xl border-2 transition-all duration-200
              ${
                selectedIndex === face.index
                  ? "border-violet-500 bg-violet-950/50 shadow-lg shadow-violet-500/20"
                  : "border-slate-600 bg-slate-800/50 hover:border-slate-500"
              }
            `}
          >
            {face.thumbnail_b64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`data:image/jpeg;base64,${face.thumbnail_b64}`}
                alt={`Face ${face.index + 1}`}
                className="w-16 h-16 rounded-lg object-cover"
              />
            ) : (
              <div className="w-16 h-16 rounded-lg bg-slate-700 flex items-center justify-center">
                <span className="text-2xl">👤</span>
              </div>
            )}
            <div className="flex items-center gap-1">
              <div
                className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${
                  selectedIndex === face.index
                    ? "border-violet-500 bg-violet-500"
                    : "border-slate-500"
                }`}
              />
              <span className="text-xs text-slate-400">Face {face.index + 1}</span>
            </div>
            {selectedIndex === face.index && (
              <div className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-violet-500 flex items-center justify-center">
                <span className="text-white text-[10px]">✓</span>
              </div>
            )}
          </button>
        ))}
      </div>
      {faces.length > 1 && (
        <p className="text-xs text-slate-500">
          {faces.length} faces detected — selected Face {selectedIndex + 1} as swap target
        </p>
      )}
    </div>
  );
}
