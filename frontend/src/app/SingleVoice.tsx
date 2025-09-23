//SingleVoice.tsx

import React, { useEffect, useMemo, useState } from "react";
import Player from "../components/shared/Player";
import { generate, toBackendUrl, getPresets, type PresetInfo } from "../api/client";
import type { ExportFormat, GenerateRequest, QualityMetrics, PlaybackRate, PresetKey } from "../types/api";

const SingleVoice: React.FC = () => {
  const [text, setText] = useState("Xin chào! Đây là bản thử nghiệm tổng hợp giọng nói bằng Piper.");
  const [voiceId, setVoiceId] = useState("vi_VN-vais1000-medium");
  const [speed, setSpeed] = useState(1.0);
  const [format, setFormat] = useState<ExportFormat>("mp3");
  const [presets, setPresets] = useState<readonly PresetInfo[]>([]);
  const [presetKey, setPresetKey] = useState<PresetKey | "">("");
  const [audioUrl, setAudioUrl] = useState<string>("");
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>("");

    // Load preset list on mount
  useEffect(() => {
    let abort = new AbortController();
    getPresets(abort.signal)
      .then((ps) => {
        setPresets(ps);
        // chọn mặc định podcast_standard nếu có
        const def = ps.find(p => p.key === "podcast_standard")?.key ?? ps[0]?.key;
        if (def) setPresetKey(def);
      })
      .catch((e) => {
        console.warn("[TTS-VTN] getPresets failed:", e);
      });
    return () => abort.abort();
  }, []);

  
  const request: GenerateRequest = useMemo(() => {
    // Clamp và cast speed về kiểu branded PlaybackRate
    const clamped = Math.min(2.0, Math.max(0.5, Number.isFinite(speed) ? speed : 1.0)) as PlaybackRate;
    return {
      mode: "sync",
      engine: "piper",
      text,
      config: { voiceId, speed: clamped, ...(presetKey ? { presetKey } : {}) },
      export: { format, bitrateKbps: format === "mp3" ? 192 : undefined },
    };
  }, [text, voiceId, speed, format, presetKey]);

  const onGenerate = async () => {
    setErr("");
    setLoading(true);
    try {
      const res = await generate(request);
      if (res.kind === "sync") {
        setAudioUrl(toBackendUrl(res.audioUrl));
        setMetrics(res.metrics);
      }
    } catch (e: any) {
      setErr(e?.message || "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "24px auto", padding: 16 }}>
      <h1 style={{ marginBottom: 8 }}>Single Voice (Piper)</h1>

      <div style={{ display: "grid", gap: 12 }}>
        <label>
          <div>Text</div>
          <textarea
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>

        <div style={{ display: "flex", gap: 12 }}>
          <label style={{ flex: 1 }}>
            <div>Voice ID</div>
            <input value={voiceId} onChange={(e) => setVoiceId(e.target.value)} style={{ width: "100%" }} />
          </label>

          <label style={{ width: 280 }}>
            <div>Speed: {speed.toFixed(2)}</div>
            <input
              type="range"
              min={0.5}
              max={2.0}
              step={0.05}
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              style={{ width: "100%" }}
            />
          </label>

          <label style={{ width: 160 }}>
            <div>Format</div>
            <select value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)} style={{ width: "100%" }}>
              <option value="mp3">mp3</option>
              <option value="wav">wav</option>
              <option value="flac">flac</option>
              <option value="m4a">m4a</option>
            </select>
          </label>
          <label style={{ width: 240 }}>
            <div>Preset</div>
            <select
              value={presetKey}
              onChange={(e) => setPresetKey(e.target.value as PresetInfo["key"] | "")}
              style={{ width: "100%" }}
            >
              <option value="">(none / Phase 1 fallback)</option>
              {presets.map(p => (
                <option key={p.key} value={p.key}>
                  {p.title} ({p.lufsTarget} LUFS)
                </option>
              ))}
            </select>
          </label>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onGenerate} disabled={loading || !text.trim()}>
            {loading ? "Generating..." : "Generate"}
          </button>
          {err && <span style={{ color: "crimson" }}>{err}</span>}
        </div>

        <div>
          <Player src={audioUrl} />
          {metrics && (
            <div style={{ marginTop: 8, fontFamily: "monospace", display: "grid", gap: 6, padding: 8, border: "1px solid #333", borderRadius: 6 }}>
              {(() => {
                const s = metrics.qualityScore ?? null;
                const badge = (score: number) => {
                  const bg = score >= 90 ? "#1f8f4d" : score >= 75 ? "#b8860b" : "#b22222";
                  return <span style={{ background: bg, color: "white", padding: "2px 8px", borderRadius: 999 }}>{score}/100</span>;
                };
                const fmtSilences = (arr: number[]) =>
                  arr.map(ms => (ms >= 1000 ? (ms/1000).toFixed(1)+"s" : ms+"ms")).join(", ");
                return (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong>Quality</strong>:{' '}{typeof s === "number" ? badge(s) : "—"}
                    </div>
                    <div><strong>LUFS</strong>: {metrics.lufsIntegrated.toFixed(2)}</div>
                    <div><strong>True Peak dB</strong>: {metrics.truePeakDb.toFixed(2)}</div>
                    <div><strong>Duration</strong>: {metrics.durationSec.toFixed(2)}s</div>
                    {"rms" in metrics && metrics.rms !== undefined && <div><strong>RMS</strong>: {metrics.rms.toFixed(2)} dBFS</div>}
                    {"crestFactor" in metrics && metrics.crestFactor !== undefined && <div><strong>Crest</strong>: {metrics.crestFactor.toFixed(2)} dB</div>}
                    {"snrApprox" in metrics && metrics.snrApprox !== undefined && <div><strong>SNR≈</strong>: {metrics.snrApprox.toFixed(1)} dB</div>}
                    {"clippingCount" in metrics && metrics.clippingCount !== undefined && <div><strong>Clipping</strong>: {metrics.clippingCount}</div>}
                    {"silenceGapsMs" in metrics && Array.isArray(metrics.silenceGapsMs) && metrics.silenceGapsMs.length > 0 && (
                      <div><strong>Silences</strong>: {fmtSilences(metrics.silenceGapsMs as number[])}</div>
                    )}
                    {"warnings" in metrics && Array.isArray(metrics.warnings) && metrics.warnings.length > 0 && (
                      <div>
                        <strong>Warnings</strong>:
                        <ul style={{ margin: "4px 0 0 16px", color: "#d9534f" }}>
                          {(metrics.warnings as string[]).map((w,i) => <li key={i}>{w}</li>)}
                        </ul>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SingleVoice;
