import { useEffect, useRef, useState } from "react";
import type { GenerateRequest, SyncGenerateResponse, JobStatusResponse, GenerateResponse } from "../types/api";
import { generate, getStatus, getResult } from "../api/client";

type JobMode = "sync" | "async";

type JobData = {
  mode?: JobMode;                 // xác định sau khi gọi generate()
  isRunning: boolean;
  jobId?: string;
  status?: JobStatusResponse;
  result?: SyncGenerateResponse;
  progress?: number;
  error?: string | null;
};

export function useTTSJob() {
  const [state, setState] = useState<JobData>({ isRunning: false, error: null });
  const timer = useRef<number | null>(null);

  function clearTimer() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
  }

  async function start(req: GenerateRequest) {
    clearTimer();
    setState({ isRunning: true, error: null });

    try {
      // 🚫 Không quan tâm req.mode; BE tự quyết Piper=sync / XTTS=async
      const res: GenerateResponse = await generate(req);

      if (res.mode === "sync") {
        setState({ mode: "sync", isRunning: false, result: res });
        return;
      }

      // async polling
      setState({ mode: "async", isRunning: true, jobId: res.jobId, progress: 0 });
      timer.current = window.setInterval(async () => {
        try {
          const st = await getStatus(res.jobId);
          setState(s => ({ ...s, status: st, progress: st.progress ?? s.progress }));

          if (st.state === "done") {
            clearTimer();
            const out = st.result ?? (await getResult(res.jobId));
            setState({
              mode: "async",
              isRunning: false,
              jobId: res.jobId,
              status: st,
              result: out,
              progress: 100,
              error: null,
            });
          } else if (st.state === "error") {
            clearTimer();
            setState({
              mode: "async",
              isRunning: false,
              jobId: res.jobId,
              status: st,
              error: st.error?.message ?? "Worker error",
            });
          }
        } catch (e: any) {
          clearTimer();
          setState(s => ({ ...s, isRunning: false, error: e?.message ?? "Polling failed" }));
        }
      }, 1000);
    } catch (e: any) {
      setState({ isRunning: false, error: e?.message ?? "Generate failed" });
    }
  }

  useEffect(() => () => clearTimer(), []);

  return { state, start };
}
