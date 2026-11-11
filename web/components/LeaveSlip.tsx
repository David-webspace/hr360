"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Seal } from "@/components/Seal";
import { hours, span, STATUS } from "@/lib/format";
import type { DocumentNote } from "@/lib/types";

type Props = {
  id: number;
  mode: "draft" | "approval";
  employee: string;
  leaveName: string;
  start: string;
  end: string;
  hoursValue: number;
  approver?: string | null;
  balance?: { before: number; after: number };
  warnings?: string[];
  reason?: string | null;
  initialStatus?: string;
  documents?: DocumentNote[];
};

async function post(path: string, body?: unknown): Promise<string | null> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.ok) return null;
  const data = (await res.json().catch(() => ({}))) as { detail?: string };
  return data.detail ?? "操作失敗，請稍後再試";
}

export function LeaveSlip(p: Props) {
  const router = useRouter();
  const [status, setStatus] = useState(p.initialStatus ?? (p.mode === "draft" ? "draft" : "pending"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(path: string, next: string, body?: unknown) {
    setBusy(true);
    setError(null);
    const err = await post(path, body);
    setBusy(false);
    if (err) return setError(err);
    setStatus(next);
    // 簽核匣不立即重抓：讓主管看到蓋章結果，下次進頁面才從清單移除
    if (p.mode === "draft") router.refresh();
  }

  const s = STATUS[status];
  const selfStamped = status !== "draft" && status !== "cancelled";
  const bossStamped = status === "approved";
  const rows: [string, React.ReactNode][] = [
    ["申請人", p.employee],
    ["假別", p.leaveName],
    ["期間", span(p.start, p.end)],
    ["時數", <span key="h" className="num">{hours(p.hoursValue)}</span>],
  ];
  if (p.balance) rows.push(["餘額", <span key="b" className="num">{hours(p.balance.before)} → {hours(p.balance.after)}</span>]);
  if (p.approver) rows.push(["簽核主管", p.approver]);
  if (p.reason) rows.push(["事由", p.reason]);
  if (p.documents?.length) {
    rows.push(["證明文件", (
      <ul key="d" className="space-y-1.5">
        {p.documents.map((d, i) => (
          <li key={d.id ?? i} className="flex items-center gap-2">
            {/* 只有本人（有附件 id）看得到縮圖；主管只拿到判讀摘要 */}
            {d.id && (
              <a href={`/api/attachments/${d.id}`} target="_blank" rel="noopener" className="shrink-0">
                <Image src={`/api/attachments/${d.id}`} alt={d.name ?? "證明文件"} width={40} height={40} unoptimized
                  className="size-10 rounded border border-rule object-cover" />
              </a>
            )}
            <span className="min-w-0 text-xs break-words">{d.summary}</span>
          </li>
        ))}
      </ul>
    )]);
  }

  return (
    <article className="w-full max-w-md min-w-0 overflow-hidden rounded-md border border-rule bg-sheet shadow-[0_1px_0_var(--color-rule)]">
      <header className="flex items-baseline justify-between gap-3 border-b border-rule px-4 pt-3 pb-2">
        <h3 className="font-display text-xl tracking-widest">請假單</h3>
        <span className="num text-xs text-muted">No. {p.id}</span>
      </header>
      <div className="flex gap-3 p-4">
        <dl className="grid min-w-0 flex-1 grid-cols-[5.25rem_1fr] border-t border-l border-rule text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="border-r border-b border-rule bg-paper px-2 py-1.5 text-muted">{k}</dt>
              <dd className="min-w-0 border-r border-b border-rule px-2 py-1.5 break-words">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="flex shrink-0 flex-col gap-3">
          <Seal name={p.employee} label="本人" stamped={selfStamped} animate={p.mode === "draft" && !p.initialStatus} />
          <Seal name={p.approver ?? "主管"} label="主管" stamped={bossStamped} animate />
        </div>
      </div>
      {p.warnings && p.warnings.length > 0 && (
        <ul className="mx-4 mb-3 space-y-1 text-xs text-muted">
          {p.warnings.map((w) => <li key={w}>・{w}</li>)}
        </ul>
      )}
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-rule px-4 py-3">
        <span className={`rounded-full border px-2.5 py-0.5 text-xs ${s.tone}`}>{s.label}</span>
        <div className="flex gap-2">
          {p.mode === "draft" && status === "draft" && (
            <>
              <button disabled={busy} onClick={() => act(`/api/leave/requests/${p.id}/cancel`, "cancelled")}
                className="rounded px-3 py-1.5 text-sm text-muted hover:text-ink disabled:opacity-50">刪除草稿</button>
              <button disabled={busy} onClick={() => act(`/api/leave/requests/${p.id}/submit`, "pending")}
                className="rounded bg-river px-4 py-1.5 text-sm text-white hover:bg-river-deep disabled:opacity-50">確認送出</button>
            </>
          )}
          {p.mode === "approval" && status === "pending" && (
            <>
              <button disabled={busy} onClick={() => act(`/api/approvals/${p.id}`, "rejected", { approve: false })}
                className="rounded border border-seal px-3 py-1.5 text-sm text-seal hover:bg-seal hover:text-white disabled:opacity-50">退回</button>
              <button disabled={busy} onClick={() => act(`/api/approvals/${p.id}`, "approved", { approve: true })}
                className="rounded bg-river px-4 py-1.5 text-sm text-white hover:bg-river-deep disabled:opacity-50">核准</button>
            </>
          )}
        </div>
      </footer>
      {error && <p role="alert" className="border-t border-rule px-4 py-2 text-sm text-seal">{error}</p>}
    </article>
  );
}
