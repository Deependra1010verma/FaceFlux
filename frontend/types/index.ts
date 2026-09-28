export type JobStatus =
  | "QUEUED"
  | "ANALYZING"
  | "DETECTING"
  | "TRACKING"
  | "SWAPPING"
  | "ENHANCING"
  | "ENCODING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type GenStatus =
  | "QUEUED"
  | "UPLOADING"
  | "GENERATING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface GenJob {
  job_id: string;
  status: GenStatus;
  progress: number;
  stage_message: string;
  error_message: string | null;
  output_ready: boolean;
  provider: string | null;
  created_at: number;
  completed_at: number | null;
}

export type TryOnStatus =
  | "QUEUED"
  | "EXTRACTING"
  | "PROCESSING"
  | "ASSEMBLING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface TryOnJob {
  job_id: string;
  status: TryOnStatus;
  progress: number;
  stage_message: string;
  error_message: string | null;
  output_ready: boolean;
  total_frames: number;
  processed_frames: number;
  created_at: number;
  completed_at: number | null;
}

export interface FaceInfo {
  index: number;
  bbox: [number, number, number, number];
  score: number;
  thumbnail_b64: string | null;
}

export interface VideoMeta {
  width: number;
  height: number;
  fps: number;
  duration: number;
  has_audio: boolean;
  codec: string;
  frame_count: number | null;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage_message: string;
  error_message: string | null;
  video_meta: VideoMeta | null;
  detected_faces: FaceInfo[];
  output_ready: boolean;
  created_at: number;
  started_at: number | null;
  completed_at: number | null;
}

export interface JobProgress {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage_message: string;
  error_message: string | null;
  output_ready: boolean;
}

export interface UploadResponse {
  upload_id: string;
  filename: string;
  size_bytes: number;
  path: string;
}

export interface SystemInfo {
  cpu: string;
  cpu_cores: number;
  ram_gb: number;
  gpu: string;
  vram_gb: number;
  acceleration: string;
  model_dir: string;
  output_dir: string;
  max_video_size_mb: number;
  default_quality: string;
  gfpgan_available: boolean;
}

export type Quality = "fast" | "balanced" | "high";
