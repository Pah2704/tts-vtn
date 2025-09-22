import React, { useMemo, useState } from "react";
import Player from "../components/shared/Player";
import { generate, toBackendUrl } from "../api/client";
import type { ExportFormat, GenerateRequest, QualityMetrics } from "../types/api";

const SingleVoice: React.FC = () => {
  const [text, setText] = useState("Xin chào! Đây là bản thử nghiệm tổng hợp giọng nói bằng Piper.");
  const [voiceId, setVoiceId] = useState("vi_VN-vais1000-medium");
  const [speed, setSpeed] = useState(1.0);
  const [format, setFormat] = useState<ExportFormat>("mp3");
  const [audioUrl, setAudioUrl] = useState<string>("");
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>("");

  const request: GenerateRequest = useMemo(() => ({
    mode: "sync",
    engine: "piper",
    text,
    config: { voiceId, speed },
    export: { format, bitrateKbps: format === "mp3" ? 192 : undefined },
  }), [text, voiceId, speed, format]);

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
            <div style={{ marginTop: 8, fontFamily: "monospace" }}>
              <div>LUFS: {metrics.lufsIntegrated.toFixed(2)}</div>
              <div>True Peak dB: {metrics.truePeakDb.toFixed(2)}</div>
              <div>Duration: {metrics.durationSec.toFixed(2)}s</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SingleVoice;
