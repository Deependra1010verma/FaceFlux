"use client";

import { useState, useEffect } from "react";
import { getApiBaseUrl, setApiBaseUrl } from "@/lib/api";
import { Server, Wifi, WifiOff, Check, RefreshCw, Globe, Sparkles, X } from "lucide-react";

interface ServerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onServerChange: (newUrl: string) => void;
}

export function ServerModal({ isOpen, onClose, onServerChange }: ServerModalProps) {
  const [url, setUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      setUrl(getApiBaseUrl());
      setTestResult(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleTest = async (testUrl?: string) => {
    const target = (testUrl || url).trim().replace(/\/+$/, "");
    if (!target) {
      setTestResult({ ok: false, message: "URL khali nahi ho sakti" });
      return false;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const res = await fetch(`${target}/health`, {
        signal: controller.signal,
        headers: {
          "Bypass-Tunnel-Reminder": "true",
        },
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        setTestResult({
          ok: true,
          message: `Connected successfully! (${data.message || "Ready"})`,
        });
        return true;
      } else {
        setTestResult({
          ok: false,
          message: `Server ne error return kiya: HTTP ${res.status}`,
        });
        return false;
      }
    } catch {
      setTestResult({
        ok: false,
        message: "Server se connect nahi ho paya. URL aur running status check karein.",
      });
      return false;
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    const cleanUrl = url.trim().replace(/\/+$/, "");
    setApiBaseUrl(cleanUrl);
    onServerChange(cleanUrl);
    onClose();
  };

  const handlePreset = (presetUrl: string) => {
    setUrl(presetUrl);
    handleTest(presetUrl);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700 shadow-2xl p-6 space-y-5 text-white">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-violet-600/20 text-violet-400 border border-violet-500/30">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-base">Backend Server Settings</h3>
              <p className="text-xs text-slate-400">Local, Cloudflare Tunnel, ya Colab GPU switch karein</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Quick Presets */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Quick Switch Presets:
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handlePreset("http://127.0.0.1:8000")}
              className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-700 bg-slate-800/60 hover:bg-slate-800 hover:border-violet-500/50 transition text-left"
            >
              <Globe className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-slate-200">Local PC</p>
                <p className="text-[10px] text-slate-500">127.0.0.1:8000</p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => {
                const sample = url.includes("trycloudflare") || url.includes("loca.lt") ? url : "";
                if (sample) handleTest(sample);
              }}
              className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-700 bg-slate-800/60 hover:bg-slate-800 hover:border-violet-500/50 transition text-left"
            >
              <Sparkles className="w-4 h-4 text-violet-400 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-slate-200">Cloud Tunnel</p>
                <p className="text-[10px] text-slate-500">Colab / Cloudflare</p>
              </div>
            </button>
          </div>
        </div>

        {/* URL Input */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Active Server URL:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setTestResult(null);
              }}
              placeholder="e.g. https://xxx.trycloudflare.com ya http://127.0.0.1:8000"
              className="flex-1 px-3 py-2 text-xs rounded-xl bg-slate-950 border border-slate-700 focus:border-violet-500 focus:outline-none text-slate-200"
            />
            <button
              type="button"
              onClick={() => handleTest()}
              disabled={testing}
              className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs font-medium text-slate-200 flex items-center gap-1.5 transition disabled:opacity-50"
            >
              {testing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
              Test
            </button>
          </div>
        </div>

        {/* Test Result Message */}
        {testResult && (
          <div
            className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
              testResult.ok
                ? "bg-emerald-950/40 border-emerald-700/50 text-emerald-300"
                : "bg-red-950/40 border-red-700/50 text-red-300"
            }`}
          >
            {testResult.ok ? (
              <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-400 flex-shrink-0" />
            )}
            <span>{testResult.message}</span>
          </div>
        )}

        <div className="text-[11px] text-slate-400 bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 leading-relaxed">
          💡 <strong>Persistent Storage:</strong> Yeh link aapke browser ke <code>localStorage</code> me save rahega, toh page refresh karne par kabhi hat nahi jayega!
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2 rounded-xl border border-slate-700 bg-slate-800/60 hover:bg-slate-800 text-xs font-semibold text-slate-300 transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="flex-1 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-xs font-semibold text-white shadow-lg shadow-violet-900/30 transition"
          >
            Save & Connect
          </button>
        </div>
      </div>
    </div>
  );
}
