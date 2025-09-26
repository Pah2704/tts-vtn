import { renderHook, act } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { useTTSJob } from "./useTTSJob";
import type {
  GenerateRequest,
  SyncGenerateResponse,
  JobStatusResponse,
} from "../types/api";

vi.mock("../api/client", async () => ({
  generate: vi.fn(),
  getStatus: vi.fn(),
  getResult: vi.fn(),
}));

import { generate, getStatus, getResult } from "../api/client";

const baseRequest: GenerateRequest = {
  engine: "xtts",
  text: "xin chào",
  config: { voiceId: "vi_VN-vais1000-medium" },
  export: { format: "mp3", bitrateKbps: 192 },
};

const syncResponse: SyncGenerateResponse = {
  mode: "sync",
  engine: "piper",
  url: "http://localhost:8000/outputs/out.mp3",
  filename: "out.mp3",
  format: "mp3",
  metrics: { lufsIntegrated: -16, truePeakDb: -1, durationSec: 1 },
};

describe("useTTSJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(generate).mockReset();
    vi.mocked(getStatus).mockReset();
    vi.mocked(getResult).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns sync result immediately", async () => {
    vi.mocked(generate).mockResolvedValue(syncResponse);

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state.mode).toBe("sync");
    expect(result.current.state.isRunning).toBe(false);
    expect(result.current.state.result).toEqual(syncResponse);
    expect(result.current.state.error ?? null).toBeNull();
    expect(getStatus).not.toHaveBeenCalled();
    expect(getResult).not.toHaveBeenCalled();
  });

  it("polls async job until done and uses embedded result", async () => {
    vi.mocked(generate).mockResolvedValue({ mode: "async", engine: "xtts", jobId: "job-1" });

    const statuses: JobStatusResponse[] = [
      { jobId: "job-1", state: "queued", progress: 0 },
      { jobId: "job-1", state: "processing", progress: 50 },
      {
        jobId: "job-1",
        state: "done",
        progress: 100,
        result: syncResponse,
      },
    ];
    let idx = 0;
    vi.mocked(getStatus).mockImplementation(async () => {
      return statuses[Math.min(idx++, statuses.length - 1)];
    });

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state).toMatchObject({
      mode: "async",
      isRunning: true,
      jobId: "job-1",
      progress: 0,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state.status?.state).toBe("queued");
    expect(result.current.state.progress).toBe(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state.status?.state).toBe("processing");
    expect(result.current.state.progress).toBe(50);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state.isRunning).toBe(false);
    expect(result.current.state.progress).toBe(100);
    expect(result.current.state.result).toEqual(syncResponse);
    expect(result.current.state.error ?? null).toBeNull();
    expect(getResult).not.toHaveBeenCalled();
  });

  it("fetches result when status is done without payload", async () => {
    vi.mocked(generate).mockResolvedValue({ mode: "async", engine: "xtts", jobId: "job-2" });

    const statuses: JobStatusResponse[] = [
      { jobId: "job-2", state: "processing", progress: 20 },
      { jobId: "job-2", state: "done", progress: 100 },
    ];
    let idx = 0;
    vi.mocked(getStatus).mockImplementation(async () => {
      return statuses[Math.min(idx++, statuses.length - 1)];
    });
    vi.mocked(getResult).mockResolvedValue(syncResponse);

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state.jobId).toBe("job-2");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state.status?.state).toBe("processing");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.state.result).toEqual(syncResponse);
    expect(result.current.state.progress).toBe(100);
    expect(result.current.state.error ?? null).toBeNull();
    expect(getResult).toHaveBeenCalledWith("job-2");
  });

  it("surfaces worker errors from status", async () => {
    vi.mocked(generate).mockResolvedValue({ mode: "async", engine: "xtts", jobId: "job-3" });
    vi.mocked(getStatus).mockResolvedValue({
      jobId: "job-3",
      state: "error",
      error: { code: "WORKER_ERROR", message: "Worker exploded" },
    });

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state.jobId).toBe("job-3");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.isRunning).toBe(false);
    expect(result.current.state.error).toBe("Worker exploded");
    expect(result.current.state.status?.state).toBe("error");
  });

  it("stops polling when status request throws", async () => {
    vi.mocked(generate).mockResolvedValue({ mode: "async", engine: "xtts", jobId: "job-4" });
    vi.mocked(getStatus).mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state.jobId).toBe("job-4");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.isRunning).toBe(false);
    expect(result.current.state.error).toBe("network down");
  });

  it("returns error when generate rejects", async () => {
    vi.mocked(generate).mockRejectedValue(new Error("bad request"));

    const { result } = renderHook(() => useTTSJob());

    await act(async () => {
      await result.current.start(baseRequest);
    });

    expect(result.current.state.isRunning).toBe(false);
    expect(result.current.state.error).toBe("bad request");
  });
});
