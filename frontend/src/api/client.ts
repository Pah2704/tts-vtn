import type {
  GenerateFn,
  GetStatusFn,
  DownloadResultFn,
  ExportFormat,
  GenerateResponse,
} from "../types/api";

// Fallback thông minh: nếu không set ENV thì dùng host hiện tại + :8000
const fallbackBase = (() => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000/api`;
  }
  return "http://localhost:8000/api";
})();
const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? fallbackBase;

// origin (http://host:port) để ghép với đường dẫn /outputs/...
const API_ORIGIN = (() => {
  try { return new URL(API_BASE).origin; } catch { return "http://localhost:8000"; }
})();

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) msg += `: ${typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)}`;
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const generate: GenerateFn = async (req, signal) => {
  // Debug nhẹ để nhìn thấy base trong console
  if (typeof window !== "undefined") {
    console.debug("[TTS-VTN] API_BASE:", API_BASE);
  }
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  return handleJson<GenerateResponse>(res);
};

export const getStatus: GetStatusFn = async (jobId, signal) => {
  const res = await fetch(`${API_BASE}/status/${encodeURIComponent(jobId)}`, { signal });
  return handleJson(res);
};

export const downloadResult: DownloadResultFn = async (jobId, format: ExportFormat = "wav", signal) => {
  const res = await fetch(`${API_BASE}/result/${encodeURIComponent(jobId)}?format=${format}`, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
};

// GHÉP URL /outputs/... thành URL đầy đủ
export function toBackendUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return "";
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  const p = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  return `${API_ORIGIN}${p}`;
}
