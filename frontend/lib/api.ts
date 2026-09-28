import type {
  GenJob,
  Job,
  JobProgress,
  Quality,
  SystemInfo,
  TryOnJob,
  UploadResponse,
} from "@/types";

const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
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
    xhr.open("POST", `${BASE}${path}`);
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
  await fetch(`${BASE}/jobs/${jobId}`, { method: "DELETE" });
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`${BASE}/jobs/${jobId}/cancel`, { method: "POST" });
}

export function getOutputUrl(jobId: string): string {
  return `${BASE}/jobs/${jobId}/output`;
}

// ── SSE Progress Stream ───────────────────────────────────────────────────────

export function streamJobProgress(
  jobId: string,
  onMessage: (progress: JobProgress) => void,
  onDone: () => void,
  onError: (err: Error) => void
): () => void {
  const es = new EventSource(`${BASE}/jobs/${jobId}/stream`);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as JobProgress;
      onMessage(data);
      if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "CANCELLED") {
        es.close();
        onDone();
      }
    } catch (e) {
      onError(new Error("Failed to parse SSE message"));
    }
  };

  es.onerror = () => {
    es.close();
    onError(new Error("SSE connection error"));
  };

  return () => es.close();
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
  return `${BASE}/generate/${jobId}/output`;
}

export async function cancelGenJob(jobId: string): Promise<void> {
  await fetch(`${BASE}/generate/${jobId}/cancel`, { method: "POST" });
}

export function streamGenProgress(
  jobId: string,
  onMessage: (job: GenJob) => void,
  onError: (err: Error) => void
): () => void {
  const es = new EventSource(`${BASE}/generate/${jobId}/stream`);

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
  return `${BASE}/tryon/${jobId}/output`;
}

export async function cancelTryOnJob(jobId: string): Promise<void> {
  await fetch(`${BASE}/tryon/${jobId}/cancel`, { method: "POST" });
}

export function streamTryOnProgress(
  jobId: string,
  onMessage: (job: TryOnJob) => void,
  onError: (err: Error) => void
): () => void {
  const es = new EventSource(`${BASE}/tryon/${jobId}/stream`);

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
