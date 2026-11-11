import type { Turn } from "@/components/ai/ChatProvider";
import { LeaveSlip } from "@/components/LeaveSlip";
import { Markdown } from "@/components/Markdown";

const TOOL_LABEL: Record<string, string> = {
  get_leave_balance: "假勤帳本", get_overtime_pay: "加班費計算", get_team_leave_summary: "團隊出勤",
  get_salary: "薪資", get_payslip: "薪資單", get_insurance_summary: "勞健保", get_travel_subsidy: "旅遊補助",
  draft_leave_request: "建立假單草稿", search_policy: "規章檢索", create_hr_ticket: "開立工單", find_employee: "通訊錄",
};

export function AiReply({ t, name }: { t: Extract<Turn, { role: "assistant" }>; name: string }) {
  return (
    <article className="min-w-0 space-y-3 border-l-2 border-river pl-3">
      <Markdown text={t.text} />
      {t.drafts.map((d) => (
        <LeaveSlip key={d.draft_id} id={d.draft_id} mode="draft" employee={d.employee ?? name} leaveName={d.leave_name}
          start={d.start} end={d.end} hoursValue={d.hours} approver={d.approver} warnings={d.warnings} initialStatus={d.status}
          documents={d.attachments}
          balance={d.balance_before !== undefined && d.balance_after !== undefined ? { before: d.balance_before, after: d.balance_after } : undefined} />
      ))}
      {t.citations.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 text-xs">
          {t.citations.map((c) => (
            <li key={c.section} className="rounded border border-rule bg-sheet px-2 py-0.5 text-muted">
              {c.section.split(" > ").slice(1).join(" ")}
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-muted">
        {t.tools.map((x) => TOOL_LABEL[x.name] ?? x.name).join("、") || "未查詢資料"}
        {t.latencyMs !== undefined && <> · <span className="num">{(t.latencyMs / 1000).toFixed(1)}s</span></>}
        {!t.groundingOk && " · 部分數字未能核對"}
      </p>
    </article>
  );
}
