import Link from "next/link";
import { Suspense } from "react";
import { apiGet } from "@/lib/api";
import type { Me, Ticket } from "@/lib/types";

const CATEGORY: Record<string, string> = {
  leave: "假勤", payroll: "薪資", insurance: "保險", benefits: "福利", policy: "規章", harassment: "性騷擾申訴",
  dispute: "爭議", other: "其他",
};
const STATE: Record<string, string> = { open: "待處理", in_progress: "處理中", resolved: "已解決", closed: "已結案" };

async function List() {
  const [me, rows] = await Promise.all([apiGet<Me>("/api/me"), apiGet<Ticket[]>("/api/tickets")]);
  return (
    <>
      <p className="mt-1 mb-6 text-sm text-muted">
        {me.is_hr ? "你看得到全公司的一般工單；機密工單只有人資經理看得到。" : "HR 助理答不了的問題會轉成工單，人資回覆後會更新狀態。"}
      </p>
      {rows.length === 0 ? (
        <p className="text-muted">目前沒有工單。</p>
      ) : (
        <ul className="divide-y divide-rule overflow-hidden rounded-md border border-rule bg-sheet">
          {rows.map((t) => (
            <li key={t.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
              <span className="num w-12 text-sm text-muted">#{t.id}</span>
              <span className={`text-sm ${t.confidential ? "text-seal" : "text-river"}`}>{CATEGORY[t.category] ?? t.category}</span>
              <span className="min-w-0 flex-1 break-words">{t.summary}</span>
              {me.is_hr && <span className="text-xs text-muted">{t.requester}</span>}
              <span className="text-xs text-muted">{STATE[t.status] ?? t.status}・{t.created_at.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function TicketsPage() {
  return (
    <>
      <h1 className="font-display text-2xl">工單</h1>
      <Suspense fallback={<p className="text-muted">讀取工單…</p>}>
        <List />
      </Suspense>
      <p className="mt-8 text-sm md:hidden">
        <Link href="/tokens" className="text-river hover:underline">連接 AI 工具（MCP 權杖）</Link>
      </p>
    </>
  );
}
