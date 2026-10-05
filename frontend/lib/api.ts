import type {
  GenJob,
  Job,
  JobProgress,
  Quality,
  SystemInfo,
  TryOnJob,
  UploadResponse,
} from "@/types";

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    try {
      const saved = localStorage.getItem("faceflux_api_url");
      if (saved && saved.trim()) {
        return saved.trim().replace(/\/+$/, "");
      }
    } catch {}
  }
  return (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export function setApiBaseUrl(url: string): void {
  if (typeof window !== "undefined") {
    try {
      if (url && url.trim()) {
        localStorage.setItem("faceflux_api_url", url.trim().replace(/\/+$/, ""));
      } else {
        localStorage.removeItem("faceflux_api_url");
      }
    } catch {}
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getApiBaseUrl();
  const headers = new Headers(options.headers || {});
  headers.set("Bypass-Tunnel-Reminder", "true");

  const res = await fetch(`${base}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ── System ───────────────────────────────────────────────────────────────────

export async function fetchSystemInfo(): Promise<SystemInfo> {
  return apiRequest<SystemInfo>("/system-info");
}

export async function fetchHealth(): Promise<{ status: string; local: boolean; message: string }> {
  return apiRequest("/health");
}

// ── Upload with progress ──────────────────────────────────────────────────────

function uploadWithProgress<T>(
  path: string,
  file: File,
  onProgress: (pct: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch {
          reject(new Error("Invalid JSON response"));
        }
      } else {
        let detail = `HTTP ${xhr.status}`;
        try {
          const body = JSON.parse(xhr.responseText);
          detail = body.detail || detail;
        } catch {}
        reject(new Error(detail));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.open("POST", `${getApiBaseUrl()}${path}`);
    xhr.setRequestHeader("Bypass-Tunnel-Reminder", "true");
    xhr.send(form);
  });
}

export async function uploadVideo(
  file: File,
  onProgress?: (pct: number) => void
): Promise<UploadResponse> {
  return uploadWithProgress<UploadResponse>("/upload/video", file, onProgress ?? (() => {}));
}

export async function uploadFace(
  file: File,
  onProgress?: (pct: number) => void
): Promise<UploadResponse> {
  return uploadWithProgress<UploadResponse>("/upload/face", file, onProgress ?? (() => {}));
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export async function createJob(params: {
  video_upload_id: string;
  face_upload_id?: string;
  face_upload_ids?: string[];
  target_face_index: number;
  quality: Quality;
  enhance: boolean;
}): Promise<Job> {
  return apiRequest<Job>("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function getJob(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${jobId}`);
}

export async function getJobProgress(jobId: string): Promise<JobProgress> {
  return apiRequest<JobProgress>(`/jobs/${jobId}/progress`);
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${getApiBaseUrl()}/jobs/${jobId}`, {
    method: "DELETE",
    headers: { "Bypass-Tunnel-Reminder": "true" },
  });
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`${getApiBaseUrl()}/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: { "Bypass-Tunnel-Reminder": "true" },
  });
}

export function getOutputUrl(jobId: string): string {
  return `${getApiBaseUrl()}/jobs/${jobId}/output`;
}

// ── SSE Progress Stream ───────────────────────────────────────────────────────

export function streamJobProgress(
  jobId: string,
  onMessage: (progress: JobProgress) => void,
  onDone: () => void,
  onError: (err: Error) => void
): () => void {
  let es: EventSource | null = null;
  let stopped = false;
  let retryCount = 0;
  const MAX_RETRIES = 8;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  function connect() {
    if (stopped) return;

    es = new EventSource(`${getApiBaseUrl()}/jobs/${jobId}/stream`);

    es.onmessage = (event) => {
      retryCount = 0; // reset on successful message
      try {
        const data = JSON.parse(event.data) as JobProgress;
        onMessage(data);
        if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "CANCELLED") {
          stopped = true;
          es?.close();
          onDone();
        }
      } catch {
        onError(new Error("Failed to parse SSE message"));
      }
    };

    es.onerror = () => {
      es?.close();
      if (stopped) return;

      if (retryCount >= MAX_RETRIES) {
        // Fallback: poll via HTTP every 2s
        stopped = true;
        _pollFallback(jobId, onMessage, onDone, onError);
        return;
      }

      // Exponential backoff: 1s, 2s, 4s, 8s ... up to 16s
      const delay = Math.min(1000 * Math.pow(2, retryCount), 16000);
      retryCount++;
      retryTimer = setTimeout(connect, delay);
    };
  }

  connect();

  return () => {
    stopped = true;
    if (retryTimer) clearTimeout(retryTimer);
    es?.close();
  };
}

/** HTTP polling fallback when SSE keeps failing */
async function _pollFallback(
  jobId: string,
  onMessage: (progress: JobProgress) => void,
  onDone: () => void,
  onError: (err: Error) => void
): Promise<void> {
  let attempts = 0;
  const MAX_POLL = 300; // 300 * 2s = 10 min max

  while (attempts < MAX_POLL) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const data = await apiRequest<JobProgress>(`/jobs/${jobId}/progress`);
      onMessage(data);
      if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "CANCELLED") {
        onDone();
        return;
      }
    } catch (e) {
      if (attempts > 5) {
        onError(e instanceof Error ? e : new Error("Poll failed"));
        return;
      }
    }
    attempts++;
  }
  onError(new Error("Job timed out after 10 minutes of polling"));
}

// ── Generate (Image → Video) ──────────────────────────────────────────────────

export async function createGenJob(params: {
  image_upload_id: string;
  prompt: string;
  duration: number;
  provider_mode?: string;
  hf_token?: string;
  colab_url?: string;
}): Promise<GenJob> {
  return apiRequest<GenJob>("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function getGenJob(jobId: string): Promise<GenJob> {
  return apiRequest<GenJob>(`/generate/${jobId}`);
}

export function getGenOutputUrl(jobId: string): string {
  return `${getApiBaseUrl()}/generate/${jobId}/output`;
}

export async function cancelGenJob(jobId: string): Promise<void> {
  await fetch(`${getApiBaseUrl()}/generate/${jobId}/cancel`, {
    method: "POST",
    headers: { "Bypass-Tunnel-Reminder": "true" },
  });
}

export function streamGenProgress(
  jobId: string,
  onMessage: (job: GenJob) => void,
  onError: (err: Error) => void
): () => void {
  const es = new EventSource(`${getApiBaseUrl()}/generate/${jobId}/stream`);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as GenJob;
      onMessage(data);
      if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "CANCELLED") {
        es.close();
      }
    } catch {
      onError(new Error("Failed to parse SSE message"));
    }
  };

  es.onerror = () => {
    es.close();
    onError(new Error("SSE connection error"));
  };

  return () => es.close();
}

// ── Virtual Try-On ────────────────────────────────────────────────────────────

export async function createTryOnJob(params: {
  video_upload_id: string;
  clothing_upload_id: string;
}): Promise<TryOnJob> {
  return apiRequest<TryOnJob>("/tryon", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function getTryOnJob(jobId: string): Promise<TryOnJob> {
  return apiRequest<TryOnJob>(`/tryon/${jobId}`);
}

export function getTryOnOutputUrl(jobId: string): string {
  return `${getApiBaseUrl()}/tryon/${jobId}/output`;
}

export async function cancelTryOnJob(jobId: string): Promise<void> {
  await fetch(`${getApiBaseUrl()}/tryon/${jobId}/cancel`, {
    method: "POST",
    headers: { "Bypass-Tunnel-Reminder": "true" },
  });
}

export function streamTryOnProgress(
  jobId: string,
  onMessage: (job: TryOnJob) => void,
  onError: (err: Error) => void
): () => void {
  const es = new EventSource(`${getApiBaseUrl()}/tryon/${jobId}/stream`);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as TryOnJob;
      onMessage(data);
      if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "CANCELLED") {
        es.close();
      }
    } catch {
      onError(new Error("Failed to parse SSE message"));
    }
  };

  es.onerror = () => {
    es.close();
    onError(new Error("SSE connection error"));
  };

  return () => es.close();
}
