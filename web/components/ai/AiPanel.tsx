"use client";

import { useEffect, useRef, useState } from "react";
import { useChat, type Turn } from "@/components/ai/ChatProvider";
import { Sparkle } from "@/components/ai/Sparkle";
import { LeaveSlip } from "@/components/LeaveSlip";
import { Markdown } from "@/components/Markdown";

const TOOL_LABEL: Record<string, string> = {
  get_leave_balance: "假勤帳本", get_overtime_pay: "加班費計算", get_team_leave_summary: "團隊出勤",
  get_salary: "薪資", get_payslip: "薪資單", get_insurance_summary: "勞健保", get_travel_subsidy: "旅遊補助",
  draft_leave_request: "建立假單草稿", search_policy: "規章檢索", create_hr_ticket: "開立工單", find_employee: "通訊錄",
};

function suggestionsFor(isManager: boolean): string[] {
  const base = ["我今年還剩多少特休？", "我上個月加班費怎麼算？", "幫我請下週一的特休", "育嬰留停要準備什麼？"];
  if (isManager) base.splice(2, 0, "我的團隊這一季誰請最多假？");
  return base;
}

function Reply({ t, name }: { t: Extract<Turn, { role: "assistant" }>; name: string }) {
  return (
    <article className="min-w-0 space-y-3 border-l-2 border-river pl-3">
      <Markdown text={t.text} />
      {t.drafts.map((d) => (
        <LeaveSlip key={d.draft_id} id={d.draft_id} mode="draft" employee={d.employee ?? name} leaveName={d.leave_name}
          start={d.start} end={d.end} hoursValue={d.hours} approver={d.approver} warnings={d.warnings} initialStatus={d.status}
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

export function AiPanel() {
  const { me, open, setOpen, turns, busy, send, conversations, conversationId, loadConversation, newConversation } = useChat();
  const [input, setInput] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);

  // 大括號不可省：新版瀏覽器的 scrollIntoView 會回傳 Promise，被 React 當成 cleanup 呼叫會整頁崩潰
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns, busy, open]);
  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);

  if (!open) return null;
  const name = me?.name ?? "";

  function submit() {
    const text = input;
    setInput("");
    void send(text);
  }

  return (
    <>
      <div onClick={() => setOpen(false)} className="fixed inset-0 z-30 hidden bg-ink/20 md:block lg:hidden" aria-hidden="true" />
      <aside aria-label="HR 助理"
        className="fixed inset-0 z-40 flex flex-col bg-paper md:left-auto md:w-[26rem] md:border-l md:border-rule md:shadow-xl lg:sticky lg:inset-auto lg:top-0 lg:z-auto lg:h-dvh lg:shrink-0 lg:shadow-none">
        <header className="flex items-center gap-2 border-b border-rule bg-sheet px-4 py-3">
          <Sparkle className="size-5 text-river" />
          <h2 className="font-display text-lg">HR 助理</h2>
          <select aria-label="切換對話" value={conversationId ?? ""} disabled={busy}
            onChange={(e) => (e.target.value ? void loadConversation(Number(e.target.value)) : newConversation())}
            className="ml-auto max-w-36 min-w-0 truncate rounded border border-rule bg-sheet px-2 py-1 text-xs text-muted">
            <option value="">新對話</option>
            {conversations.map((c) => <option key={c.id} value={c.id}>{c.title ?? `對話 ${c.id}`}</option>)}
          </select>
          <button onClick={newConversation} disabled={busy} title="開新對話" className="rounded px-2 py-1 text-sm text-river hover:bg-river-wash disabled:opacity-50">＋</button>
          <button onClick={() => setOpen(false)} aria-label="關閉 HR 助理" title="關閉（Ctrl／⌘ + J）" className="rounded px-2 py-1 text-muted hover:bg-paper hover:text-ink">✕</button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
          {turns.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted">{name ? `${name}，` : ""}特休、加班費、薪資單、請假與公司規定都可以問。數字由系統依勞基法與公司規定計算；假單由你按確認後才會送出。</p>
              <div className="flex flex-wrap gap-2">
                {suggestionsFor(Boolean(me?.is_manager)).map((s) => (
                  <button key={s} onClick={() => void send(s)} className="rounded-full border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-river hover:text-river">{s}</button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <p key={i} className="ml-auto w-fit max-w-[85%] rounded-md bg-river-wash px-3 py-2 text-sm break-words">{t.text}</p>
            ) : t.role === "error" ? (
              <p key={i} role="alert" className="border-l-2 border-seal pl-3 text-sm text-seal">{t.text}</p>
            ) : (
              <div key={i} className="text-sm"><Reply t={t} name={name} /></div>
            ),
          )}
          {busy && <p className="animate-pulse pl-3 text-sm text-muted motion-reduce:animate-none">查詢中…</p>}
          <div ref={end} />
        </div>

        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="flex gap-2 border-t border-rule bg-sheet p-3">
          <label htmlFor="ai-ask" className="sr-only">輸入問題</label>
          <textarea id="ai-ask" ref={field} rows={2} value={input} maxLength={2000} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="例如：幫我請下週一的特休"
            className="min-w-0 flex-1 resize-none rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:border-river focus:outline-none" />
          <button disabled={busy || !input.trim()} className="shrink-0 self-end rounded-md bg-river px-4 py-2 text-sm text-white hover:bg-river-deep disabled:opacity-40">送出</button>
        </form>
      </aside>
    </>
  );
}
