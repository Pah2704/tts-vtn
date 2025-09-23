/**
 * Module X — API DTOs (FE ↔ BE) + chữ ký hàm client (type only).
 * Không có implementation. Dùng ở bước (5) để sinh stubs trong src/api/client.ts.
 */

import type { PlaybackRate, EmotionTag, BackgroundFx } from "./audio";

/** Engine TTS khả dụng. Phase 1 dùng "piper"; "xtts" để dành Phase 3. */
export type Engine = "piper" | "xtts";

/** Định dạng export hỗ trợ. */
export type ExportFormat = "mp3" | "wav" | "flac" | "m4a";

/** Preset xử lý (Phase 2+). Đặt sẵn để khoá contract. */
export type PresetKey =
  | "podcast_standard"
  | "audiobook_professional"
  | "announcement"
  | "natural_minimal";

/** Các chỉ số chất lượng tối thiểu phải trả về UI (Phase 1). */
export interface QualityMetrics {
  /** Integrated loudness theo LUFS (âm, ví dụ -16.0). */
  readonly lufsIntegrated: number;
  /** True peak dBFS (âm, ví dụ -1.0). */
  readonly truePeakDb: number;
  /** Thời lượng giây của file cuối. */
  readonly durationSec: number;
  
// ===== Phase 2 (mở rộng in-place, giữ optional để tương thích ngược) =====
/** Root-mean-square level (dBFS approx). */
  readonly rms?: number;
  /** Crest factor = peak - rms (dB). Giá trị quá thấp → nén quá mức. */
  readonly crestFactor?: number;
  /** Ước lượng SNR (dB) dựa trên noise floor trong đoạn lặng. */
  readonly snrApprox?: number;
  /** Số mẫu/điểm clipping phát hiện được. */
  readonly clippingCount?: number;
  /** Danh sách các khoảng lặng (ms) đáng chú ý. */
  readonly silenceGapsMs?: ReadonlyArray<number>;
  /** Điểm chất lượng tổng hợp (0–100) theo rule-based QC. */
  readonly qualityScore?: number;
  /** Cảnh báo QC (ví dụ: "Low SNR", "Detected clipping"). */
  readonly warnings?: ReadonlyArray<string>;
  
}

/** Tuỳ chọn export từ BE. */
export interface ExportOptions {
  readonly format: ExportFormat;            // ví dụ "mp3"
  readonly bitrateKbps?: 128 | 192 | 256 | 320; // áp dụng cho lossy
}

/** Cấu hình giọng/đọc phía BE cần để synth đơn thoại (Phase 1). */
export interface SynthesisConfig {
  /** id giọng Piper/XTTS, do FE chọn từ list. */
  readonly voiceId: string;
  /** tốc độ 0.5–2.0 (mặc định 1.0). Caller phải validate trước. */
  readonly speed?: PlaybackRate;
  /** tag cảm xúc mức đơn giản; BE có thể bỏ qua nếu engine không hỗ trợ. */
  readonly emotions?: ReadonlyArray<EmotionTag>;
  /** hiệu ứng nền (Phase 3+); Phase 1 có thể luôn là "none". */
  readonly background?: {
    readonly kind: BackgroundFx;
    /** 0–0.5 (0–50%), mặc định 0.2; caller nên clamp trước khi gửi. */
    readonly gain?: number;
  };
  /** preset xử lý (Phase 2+); Phase 1 có thể undefined. */
  readonly presetKey?: PresetKey;
}

/**
 * Yêu cầu /generate.
 * PRE: text đã được trim, không rỗng; length ≤ 5000 cho Piper (Phase 1).
 * PRE: engine="piper" ở Phase 1; các field speed ∈ [0.5,2.0].
 * POST: Nếu chế độ sync, BE trả ngay file url + metrics.
 */
export interface GenerateRequest {
  readonly mode?: "sync" | "async"; // Phase 1 dùng "sync" mặc định
  readonly engine: Engine;          // Phase 1: "piper"
  readonly text: string;
  readonly config: SynthesisConfig;
  readonly export?: ExportOptions;  // Phase 1: mặc định "wav" hoặc "mp3"
}

/** Kết quả đồng bộ (Phase 1). */
export interface SyncGenerateResponse {
  readonly kind: "sync";
  /** URL có thể phát/tải (có thể là path tương đối). */
  readonly audioUrl: string;
  /** BE echo lại định dạng. */
  readonly format: ExportFormat;
  /** Metrics tối thiểu phải có (LUFS/Peak/Duration). */
  readonly metrics: QualityMetrics;
}

/** Kết quả bất đồng bộ (Phase 3+). */
export interface AsyncGenerateResponse {
  readonly kind: "async";
  readonly jobId: string;
}

/** Union cho /generate (Phase 1 trả Sync). */
export type GenerateResponse = SyncGenerateResponse | AsyncGenerateResponse;

// =======================
// Phase 2: /api/presets (type only)
// =======================
/** Thông tin preset để FE render dropdown/help. */
export interface PresetInfo {
  readonly key: PresetKey;
  readonly title: string;
  readonly lufsTarget: number;
  readonly description?: string;
}

/** Gọi /api/presets (trả danh sách preset khả dụng). */
export type GetPresetsFn = (
  signal?: AbortSignal
) => Promise<ReadonlyArray<PresetInfo>>;

/** Trạng thái job (dùng khi ở chế độ async Phase 3+). */
export type JobState = "queued" | "processing" | "done" | "error";

export interface JobStatusResponse {
  readonly jobId: string;
  readonly state: JobState;
  /** 0..100 (tuỳ BE có hay không). */
  readonly progress?: number;
  /** Nếu lỗi. */
  readonly error?: { readonly code: string; readonly message: string };
  /** Khi done, có thể kèm result để client khỏi gọi thêm. */
  readonly result?: SyncGenerateResponse;
}

/* =======================
   Signatures cho API client (type only)
   Sẽ được implement ở bước (5) trong src/api/client.ts
   ======================= */

/**
 * Gọi /generate.
 * PRE: req thoả điều kiện trong GenerateRequest (đặc biệt speed, text length).
 * POST: Nếu req.mode không set → mặc định "sync" và trả SyncGenerateResponse.
 * ERROR CASES: 400 (input), 500 (lỗi synth/pipeline), abort signal.
 */
export type GenerateFn = (
  req: GenerateRequest,
  signal?: AbortSignal
) => Promise<GenerateResponse>;

/**
 * Gọi /status/{jobId} (Phase 3+).
 * PRE: jobId là UUID/ID hợp lệ BE đã trả.
 * POST: Trả trạng thái hiện tại; khi "done" có thể có result.
 */
export type GetStatusFn = (
  jobId: string,
  signal?: AbortSignal
) => Promise<JobStatusResponse>;

/**
 * Tải dữ liệu âm thanh (nếu cần một API riêng hoặc /result/{jobId}).
 * POST: Trả Blob để FE tạo ObjectURL.
 */
export type DownloadResultFn = (
  jobId: string,
  format?: ExportFormat,
  signal?: AbortSignal
) => Promise<Blob>;