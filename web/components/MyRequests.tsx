"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { hours, span, STATUS } from "@/lib/format";
import type { LeaveRow } from "@/lib/types";

export function MyRequests({ rows, today }: { rows: LeaveRow[]; today: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function cancel(id: number) {
    setBusy(id);
    setError(null);
    const res = await fetch(`/api/leave/requests/${id}/cancel`, { method: "POST" });
    setBusy(null);
    if (!res.ok) {
      setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "取消失敗");
      return;
    }
    router.refresh();
  }

  const visible = rows.filter((r) => r.status !== "cancelled" && r.status !== "draft");
  if (!visible.length) return <p className="text-muted">還沒有假單。到「助理」說一聲「幫我請明天的特休」就能開始。</p>;

  return (
    <div className="overflow-hidden rounded-md border border-rule bg-sheet">
      {error && <p role="alert" className="border-b border-rule px-4 py-2 text-sm text-seal">{error}</p>}
      <ul className="divide-y divide-rule">
        {visible.map((r) => {
          const s = STATUS[r.status];
          const canCancel = r.status === "pending" || (r.status === "approved" && r.start_at.slice(0, 10) > today);
          return (
            <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
              <span className="w-full shrink-0 font-display sm:w-36">{r.leave_name}</span>
              <span className="min-w-0 flex-1 text-sm break-words">{span(r.start_at, r.end_at)}</span>
              <span className="num w-20 text-right text-sm">{hours(r.hours)}</span>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${s.tone}`}>{s.label}</span>
              {canCancel && (
                <button onClick={() => cancel(r.id)} disabled={busy === r.id} className="text-xs text-river hover:underline disabled:opacity-50">
                  取消
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
