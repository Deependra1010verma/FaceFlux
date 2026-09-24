"use client";

import { getOutputUrl } from "@/lib/api";
import { Download, Play } from "lucide-react";
import { useState } from "react";

interface VideoOutputProps {
  jobId: string;
}

export function VideoOutput({ jobId }: VideoOutputProps) {
  const outputUrl = getOutputUrl(jobId);
  const [playing, setPlaying] = useState(false);

  return (
    <div className="space-y-4">
      <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide">
        Output Preview
      </label>

      {/* Video player */}
      <div className="relative rounded-xl overflow-hidden bg-black aspect-video">
        <video
          src={outputUrl}
          controls
          className="w-full h-full"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        >
          Your browser does not support the video tag.
        </video>
      </div>

      {/* Download button */}
      <a
        href={outputUrl}
        download={`faceflux_${jobId}.mp4`}
        className="flex items-center justify-center gap-2 w-full py-3 px-4 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold transition-colors duration-200"
      >
        <Download className="w-4 h-4" />
        Save Output Video
      </a>
    </div>
  );
}
