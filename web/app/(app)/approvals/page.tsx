import { Suspense } from "react";
import { LeaveSlip } from "@/components/LeaveSlip";
import { apiGet } from "@/lib/api";
import type { LeaveRow, Me } from "@/lib/types";

async function Inbox() {
  const [me, rows] = await Promise.all([apiGet<Me>("/api/me"), apiGet<LeaveRow[]>("/api/approvals")]);
  if (!rows.length) return <p className="text-muted">目前沒有待你簽核的假單。</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {rows.map((r) => (
        <LeaveSlip key={r.id} id={r.id} mode="approval" employee={r.employee} leaveName={r.leave_name}
          start={r.start_at} end={r.end_at} hoursValue={r.hours} approver={me.name} reason={r.reason}
          documents={r.attachments} />
      ))}
    </div>
  );
}

export default function ApprovalsPage() {
  return (
    <>
      <h1 className="font-display text-2xl">簽核</h1>
      <p className="mt-1 mb-6 text-sm text-muted">只顯示直屬部屬送出的假單。病假原因與證明文件原圖不會顯示在這裡，只顯示文件判讀摘要。</p>
      <Suspense fallback={<p className="text-muted">讀取待簽假單…</p>}>
        <Inbox />
      </Suspense>
    </>
  );
}
