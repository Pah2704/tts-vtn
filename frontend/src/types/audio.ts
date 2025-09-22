/**
 * Module Y — Audio types cho FE: cấu hình giọng, emotion tags, background,
 * mô hình waveform & A/B compare. Chỉ types + chữ ký hàm (type).
 */

/** Emotion tags cơ bản (khớp tài liệu). */
export type EmotionTag =
  | "happy"
  | "sad"
  | "excited"
  | "calm"
  | "serious"
  | "whisper";

/** Hiệu ứng nền (Phase 3+). Phase 1 hãy dùng "none". */
export type BackgroundFx =
  | "none"
  | "rain"
  | "cafe"
  | "forest"
  | "ocean"
  | "fire"
  | "wind";

/**
 * Tốc độ đọc 0.5–2.0 (brand để tránh dùng nhầm).
 * Lưu ý: TypeScript không enforce range runtime; FE phải validate trước khi gán.
 */
export type PlaybackRate = number & { readonly __brand: "PlaybackRate0.5to2.0" };

/** Cấu hình chọn giọng hiện tại ở FE. */
export interface VoiceConfig {
  readonly voiceId: string;
  /** 0.5–2.0, default 1.0 — caller phải clamp trước khi lưu. */
  readonly speed: PlaybackRate;
  /** Emotion mặc định cho toàn văn bản (Single Voice). */
  readonly defaultEmotions?: ReadonlyArray<EmotionTag>;
}

/** Dữ liệu waveform dùng để vẽ (đơn giản hoá). */
export interface WaveformSeries {
  /** sampleRate của dữ liệu (Hz). */
  readonly sampleRate: number;
  /** mono=1, stereo=2. */
  readonly channels: 1 | 2;
  /**
   * Mảng giá trị -1..1 đã downsample để vẽ (ví dụ 1k–4k points).
   * FE có thể tạo từ AudioBuffer.
   */
  readonly points: ReadonlyArray<number>;
}

/** Mô hình so sánh A/B (Processed vs Original). */
export interface ABComparisonModel {
  readonly a: WaveformSeries; // Original
  readonly b: WaveformSeries; // Processed
  /** Chênh lệch RMS/LUFS ước lượng ở FE (tuỳ optional). */
  readonly delta?: {
    readonly approxRmsDb?: number;
    readonly approxLufs?: number;
  };
}

/* =======================
   Chữ ký hàm (type only) dùng cho bước (5)
   ======================= */

/**
 * Tính waveform từ nhị phân audio để vẽ UI.
 * PRE: audioData là dữ liệu đã tải/đọc; size hợp lý (< ~50MB cho FE).
 * POST: WaveformSeries đã downsample (caller cấu hình độ phân giải).
 * ERROR: Nếu parse thất bại (định dạng không hỗ trợ), reject với Error.
 */
export type ComputeWaveformFn = (
  audioData: ArrayBuffer,
  options?: { readonly maxPoints?: number }
) => Promise<WaveformSeries>;

/**
 * Tạo model so sánh A/B cho trình phát nâng cao.
 * PRE: a,b là cùng file nguồn khác phiên bản (original vs processed).
 * POST: Trả model gói sẵn cho component Player (A/B).
 */
export type BuildABComparisonFn = (
  a: ArrayBuffer,
  b: ArrayBuffer,
  options?: { readonly maxPoints?: number }
) => Promise<ABComparisonModel>;