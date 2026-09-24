import type {
  Job,
  JobProgress,
  Quality,
  SystemInfo,
  UploadResponse,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

// ── Uploads ──────────────────────────────────────────────────────────────────

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<UploadResponse>("/upload/video", {
    method: "POST",
    body: form,
  });
}

export async function uploadFace(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<UploadResponse>("/upload/face", {
    method: "POST",
    body: form,
  });
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export async function createJob(params: {
  video_upload_id: string;
  face_upload_id: string;
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
      if (data.status === "COMPLETED" || data.status === "FAILED") {
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
