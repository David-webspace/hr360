"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type TokenRow = { id: number; name: string; scope: "read" | "action"; expires_at: string; last_used_at: string | null; revoked: boolean };

export function TokenManager({ rows }: { rows: TokenRow[] }) {
  const router = useRouter();
  const [name, setName] = useState("Claude Desktop");
  const [scope, setScope] = useState<"read" | "action">("read");
  const [days, setDays] = useState(30);
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/tokens", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, scope, days }),
    });
    setBusy(false);
    if (!res.ok) return setError("建立失敗，請確認名稱與天數（1–90 天）");
    setCreated(((await res.json()) as { token: string }).token);
    router.refresh();
  }

  async function revoke(id: number) {
    await fetch(`/api/tokens/${id}/revoke`, { method: "POST" });
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <form onSubmit={create} className="grid gap-3 rounded-md border border-rule bg-sheet p-4 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
        <label className="min-w-0 text-sm">
          <span className="text-muted">用途</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={64} required
            className="mt-1 w-full rounded border border-rule px-3 py-2 focus:border-river focus:outline-none" />
        </label>
        <label className="text-sm">
          <span className="text-muted">權限</span>
          <select value={scope} onChange={(e) => setScope(e.target.value as "read" | "action")}
            className="mt-1 block w-full rounded border border-rule bg-sheet px-3 py-2">
            <option value="read">唯讀：只能查詢</option>
            <option value="action">可辦事：建立並送出假單、開工單</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="text-muted">有效天數</span>
          <input type="number" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="num mt-1 block w-24 rounded border border-rule px-3 py-2" />
        </label>
        <button disabled={busy} className="rounded bg-river px-4 py-2 text-white hover:bg-river-deep disabled:opacity-50">產生權杖</button>
      </form>
      {error && <p role="alert" className="text-sm text-seal">{error}</p>}
      {created && (
        <div className="rounded-md border border-glow bg-glow-wash p-4 text-sm">
          <p className="font-medium">權杖只顯示這一次，請現在複製保存：</p>
          <code className="num mt-2 block break-all rounded bg-sheet p-2">{created}</code>
          <button onClick={() => navigator.clipboard.writeText(created)} className="mt-2 text-river hover:underline">複製</button>
        </div>
      )}
      {rows.length > 0 && (
        <ul className="divide-y divide-rule overflow-hidden rounded-md border border-rule bg-sheet">
          {rows.map((t) => (
            <li key={t.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-sm">
              <span className="min-w-0 flex-1 break-words font-medium">{t.name}</span>
              <span className={t.scope === "action" ? "text-seal" : "text-river"}>{t.scope === "action" ? "可辦事" : "唯讀"}</span>
              <span className="text-xs text-muted">
                {t.revoked ? "已撤銷" : `到期 ${t.expires_at.slice(0, 10)}`}・{t.last_used_at ? `最後使用 ${t.last_used_at.slice(0, 10)}` : "尚未使用"}
              </span>
              {!t.revoked && <button onClick={() => revoke(t.id)} className="text-xs text-seal hover:underline">撤銷</button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
