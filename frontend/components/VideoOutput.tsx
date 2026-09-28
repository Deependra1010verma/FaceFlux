"use client";

import { getOutputUrl } from "@/lib/api";
import { Download, Image as ImageIcon } from "lucide-react";
import { useState } from "react";

interface VideoOutputProps {
  jobId: string;
  isImage?: boolean;
}

export function VideoOutput({ jobId, isImage = false }: VideoOutputProps) {
  const outputUrl = getOutputUrl(jobId);
  const [isVideoError, setIsVideoError] = useState(false);

  const showImage = isImage || isVideoError;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide">
          Output Result
        </label>
        <span className="text-[11px] text-emerald-400 font-medium">
          {showImage ? "Swapped Photo Ready" : "Swapped Video Ready"}
        </span>
      </div>

      {/* Media Player / Image Viewer */}
      <div className="relative rounded-xl overflow-hidden bg-black aspect-video flex items-center justify-center border border-slate-800">
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
      </div>

      {/* Download button */}
      <a
        href={outputUrl}
        download={showImage ? `faceflux_swap_${jobId}.jpg` : `faceflux_${jobId}.mp4`}
        className="flex items-center justify-center gap-2 w-full py-3 px-4 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold transition-colors duration-200 shadow-lg shadow-violet-600/20 active:scale-[0.98]"
      >
        <Download className="w-4 h-4" />
        {showImage ? "Save Output Photo" : "Save Output Video"}
      </a>
    </div>
  );
}
