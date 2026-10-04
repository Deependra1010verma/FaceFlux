"use client";

import { FaceInfo } from "@/types";
import { motion, AnimatePresence } from "@/lib/motion-shim";
import { CheckCircle2, User } from "lucide-react";

interface FaceGridProps {
  faces: FaceInfo[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export function FaceGrid({ faces, selectedIndex, onSelect }: FaceGridProps) {
  if (faces.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3 p-4 rounded-xl bg-slate-800/40 border border-slate-700/60"
    >
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Detected Faces — Select Target
        </label>
        <span className="text-[11px] text-violet-400 font-medium bg-violet-950/50 px-2 py-0.5 rounded-full">
          {faces.length} face{faces.length > 1 ? "s" : ""} found
        </span>
      </div>

      <div className="flex flex-wrap gap-3">
        <AnimatePresence>
          {faces.map((face) => {
            const isSelected = selectedIndex === face.index;
            const confidencePct = Math.round(face.score * 100);
            return (
              <motion.button
                key={face.index}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: face.index * 0.05 }}
                onClick={() => onSelect(face.index)}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                data-tooltip={`Face ${face.index + 1} · ${confidencePct}% confidence`}
                className={`relative flex flex-col items-center gap-1.5 p-2 rounded-xl border-2 transition-colors duration-200 cursor-pointer
                  ${
                    isSelected
                      ? "border-violet-500 bg-violet-950/60 shadow-lg shadow-violet-500/25"
                      : "border-slate-600 bg-slate-800/50 hover:border-slate-500 hover:bg-slate-800"
                  }
                `}
              >
                {/* Face thumbnail */}
                {face.thumbnail_b64 ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`data:image/jpeg;base64,${face.thumbnail_b64}`}
                    alt={`Face ${face.index + 1}`}
                    className="w-16 h-16 rounded-lg object-cover"
                  />
                ) : (
                  <div className="w-16 h-16 rounded-lg bg-slate-700 flex items-center justify-center">
                    <User className="w-7 h-7 text-slate-500" />
                  </div>
                )}

                {/* Confidence bar */}
                <div className="w-full h-1 rounded-full bg-slate-700 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isSelected ? "bg-violet-500" : "bg-slate-500"
                    }`}
                    style={{ width: `${confidencePct}%` }}
                  />
                </div>

                {/* Label */}
                <div className="flex items-center gap-1">
                  <span className={`text-xs font-medium ${isSelected ? "text-violet-300" : "text-slate-400"}`}>
                    Face {face.index + 1}
                  </span>
                  <span className="text-[10px] text-slate-600">
                    {confidencePct}%
                  </span>
                </div>

                {/* Selected checkmark */}
                {isSelected && (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="absolute -top-1.5 -right-1.5"
                  >
                    <CheckCircle2 className="w-5 h-5 text-violet-400 bg-slate-900 rounded-full" />
                  </motion.div>
                )}
              </motion.button>
            );
          })}
        </AnimatePresence>
      </div>

      {faces.length > 1 && (
        <p className="text-xs text-slate-500">
          ↑ Multiple faces detected — click to select which face to replace
        </p>
      )}
    </motion.div>
  );
}
