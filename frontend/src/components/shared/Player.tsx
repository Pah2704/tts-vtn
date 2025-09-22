import React, { useRef, useState } from "react";

/** Thu gọn props, đủ để render UI cơ bản. */
export type PlayerProps = {
  /** URL/Blob src để phát audio. */
  src?: string;
  className?: string;
  /** TODO: sau này thêm props cho A/B và waveform model. */
};

/**
 * Skeleton Player — chưa có waveform & A/B thực sự.
 * TODO: A/B toggle, waveform placeholder, time/progress, hotkeys.
 */
const Player: React.FC<PlayerProps> = ({ src, className }) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [abMode, setAbMode] = useState<"A" | "B">("A");

  return (
    <div className={className ?? ""} style={{ border: "1px dashed #ccc", padding: 12, borderRadius: 8 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button type="button" onClick={() => audioRef.current?.play()}>Play</button>
        <button type="button" onClick={() => audioRef.current?.pause()}>Pause</button>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          <label>A/B:</label>
          <select value={abMode} onChange={(e) => setAbMode(e.target.value as "A" | "B")}>
            <option value="A">A</option>
            <option value="B">B</option>
          </select>
        </div>
      </div>

      {/* TODO: waveform placeholder */}
      <div style={{ height: 64, marginTop: 8, background: "#f7f7f7", borderRadius: 4, display: "grid", placeItems: "center" }}>
        <span style={{ opacity: 0.6 }}>Waveform placeholder</span>
      </div>

      <audio ref={audioRef} src={src} controls style={{ width: "100%", marginTop: 8 }} />
    </div>
  );
};

export default Player;
