"use client";
import { useEffect, useState } from "react";
import { ApiError, runTool, type ToolResult } from "./api";

export interface ToolState { data: ToolResult | null; error: ApiError | null; loading: boolean; durationMs?: number }
export function useTool(name: string, args: Record<string, unknown> = {}): ToolState {
  const [s, setS] = useState<ToolState>({ data: null, error: null, loading: true });
  const key = name + JSON.stringify(args);
  useEffect(() => {
    let live = true;
    setS({ data: null, error: null, loading: true });
    runTool(name, args).then((r) => live && setS({ data: r.result, error: null, loading: false, durationMs: r.duration_ms }))
      .catch((e: ApiError) => live && setS({ data: null, error: e, loading: false }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return s;
}
