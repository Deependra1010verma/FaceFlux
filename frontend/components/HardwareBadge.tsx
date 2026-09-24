"use client";

import { SystemInfo } from "@/types";
import { CheckCircle, Cpu, HardDrive, Monitor, XCircle, Zap } from "lucide-react";

interface HardwareBadgeProps {
  info: SystemInfo;
}

function AccelerationBadge({ provider }: { provider: string }) {
  const isCuda = provider.includes("CUDA");
  const isRocm = provider.includes("ROCM") || provider.includes("ROCm");

  let label = "CPU";
  let colorClass = "bg-slate-700 text-slate-300";

  if (isCuda) {
    label = "CUDA GPU";
    colorClass = "bg-green-900/60 text-green-300 border border-green-700/50";
  } else if (isRocm) {
    label = "ROCm GPU";
    colorClass = "bg-orange-900/60 text-orange-300 border border-orange-700/50";
  }

  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-bold tracking-wide ${colorClass}`}>
      {label}
    </span>
  );
}

export function HardwareBadge({ info }: HardwareBadgeProps) {
  return (
    <div className="rounded-xl bg-slate-900 border border-slate-800 p-4 space-y-3">
      {/* Local processing indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
            Local Processing
          </span>
        </div>
        <span className="text-[11px] text-slate-500">
          Tumhare files iss device pe hi rahenge
        </span>
      </div>

      {/* Hardware grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="flex items-start gap-2">
          <Cpu className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">CPU</p>
            <p className="text-xs text-slate-300 font-medium">
              {info.cpu_cores} cores
            </p>
            <p
              className="text-[10px] text-slate-600 truncate max-w-[100px]"
              title={info.cpu}
            >
              {info.cpu.split("@")[0].trim()}
            </p>
          </div>
        </div>

        <div className="flex items-start gap-2">
          <HardDrive className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">RAM</p>
            <p className="text-xs text-slate-300 font-medium">{info.ram_gb} GB</p>
          </div>
        </div>

        <div className="flex items-start gap-2">
          <Monitor className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">GPU</p>
            <p
              className="text-xs text-slate-300 font-medium truncate max-w-[100px]"
              title={info.gpu}
            >
              {info.gpu === "None" ? "No GPU" : info.gpu}
            </p>
            {info.vram_gb > 0 && (
              <p className="text-[10px] text-slate-600">{info.vram_gb} GB VRAM</p>
            )}
          </div>
        </div>

        <div className="flex items-start gap-2">
          <Zap className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">Mode</p>
            <AccelerationBadge provider={info.acceleration} />
          </div>
        </div>
      </div>

      {/* GFPGAN status */}
      <div className="pt-1 border-t border-slate-800 flex items-center gap-2">
        {info.gfpgan_available ? (
          <>
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
            <span className="text-[11px] text-emerald-400">
              GFPGAN available — Face Enhancement enabled
            </span>
          </>
        ) : (
          <>
            <XCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            <span className="text-[11px] text-amber-500">
              GFPGAN not installed — Enhancement disabled.{" "}
              <code className="bg-slate-800 px-1 rounded text-[10px]">
                pip3 install --break-system-packages gfpgan
              </code>
            </span>
          </>
        )}
      </div>
    </div>
  );
}
