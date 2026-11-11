"use client";

import { useState } from "react";

type Check = { alias: string; model: string; ok: boolean; tool_call?: boolean; zh_tw_output?: boolean; latency_ms?: number; error?: string };
type Result = { provider: string; base_url: string; ok: boolean; checks: Check[] };

export function LlmCheck() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/admin/llm-check").catch(() => null);
    setBusy(false);
    if (!res?.ok) return setError("自檢沒有完成，請確認 API 服務在執行");
    setResult((await res.json()) as Result);
  }

  return (
    <section className="mb-8 rounded-md border border-rule bg-sheet p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl">模型連線自檢</h2>
          <p className="text-sm text-muted">換模型端點後先跑一次：檢查連線、工具呼叫與繁體中文輸出。</p>
        </div>
        <button onClick={run} disabled={busy} className="rounded bg-river px-4 py-1.5 text-sm text-white hover:bg-river-deep disabled:opacity-50">
          {busy ? "檢查中…" : "執行自檢"}
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-seal">{error}</p>}
      {result && (
        <div className="mt-4 text-sm">
          <p className="text-muted">{result.provider}・{result.base_url}</p>
          <ul className="mt-2 space-y-1">
            {result.checks.map((c) => (
              <li key={c.alias} className="flex flex-wrap gap-x-4">
                <span className={c.ok ? "text-river" : "text-seal"}>{c.ok ? "通過" : "未通過"}</span>
                <span className="num">{c.alias}：{c.model}</span>
                {c.error ? <span className="text-seal">{c.error}</span> : (
                  <span className="text-muted">工具呼叫 {c.tool_call ? "✓" : "✗"}・繁中 {c.zh_tw_output ? "✓" : "✗"}・{((c.latency_ms ?? 0) / 1000).toFixed(1)}s</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
