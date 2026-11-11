"use client";

import { useEffect, useRef, useState } from "react";
import { LeaveSlip } from "@/components/LeaveSlip";
import { Markdown } from "@/components/Markdown";
import type { ChatReply } from "@/lib/types";

type Turn = { role: "user"; text: string } | { role: "assistant"; reply: ChatReply } | { role: "error"; text: string };

const TOOL_LABEL: Record<string, string> = {
  get_leave_balance: "假勤帳本", get_overtime_pay: "加班費計算", get_team_leave_summary: "團隊出勤",
  get_salary: "薪資", get_payslip: "薪資單", get_insurance_summary: "勞健保", get_travel_subsidy: "旅遊補助",
  draft_leave_request: "建立假單草稿", search_policy: "規章檢索", create_hr_ticket: "開立工單", find_employee: "通訊錄",
};

export function Chat({ name, suggestions }: { name: string; suggestions: string[] }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversation, setConversation] = useState<number | null>(null);
  const end = useRef<HTMLDivElement>(null);

  // 大括號不可省：新版瀏覽器的 scrollIntoView 會回傳 Promise，被 React 當成 cleanup 呼叫就會整頁崩潰
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setTurns((t) => [...t, { role: "user", text: message }]);
    setInput("");
    setBusy(true);
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversation }),
    }).catch(() => null);
    setBusy(false);
    if (!res || !res.ok) {
      const detail = res ? ((await res.json().catch(() => ({}))) as { detail?: string }).detail : undefined;
      setTurns((t) => [...t, { role: "error", text: detail ?? "連不上 HR 助理，請檢查網路後再試一次" }]);
      return;
    }
    const reply = (await res.json()) as ChatReply;
    setConversation(reply.conversation_id);
    setTurns((t) => [...t, { role: "assistant", reply }]);
  }

  return (
    <section className="flex min-h-[calc(100dvh-8rem)] min-w-0 flex-col md:min-h-[calc(100dvh-3rem)]">
      <div className="flex items-center justify-between gap-3 pb-4">
        <h1 className="font-display text-2xl">問人資之前，先問我</h1>
        {turns.length > 0 && (
          <button onClick={() => { setTurns([]); setConversation(null); }} className="shrink-0 text-sm text-river hover:underline">
            開新對話
          </button>
        )}
      </div>

      <div className="min-w-0 flex-1 space-y-6">
        {turns.length === 0 && (
          <div className="rounded-md border border-rule bg-sheet p-5">
            <p className="text-muted">{name}，特休、加班費、薪資單、請假與公司規定都可以直接問。數字由系統依勞基法與公司規定計算，不是猜的。</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border border-rule px-3 py-1.5 text-sm hover:border-river hover:text-river">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <p key={i} className="ml-auto w-fit max-w-[85%] rounded-md bg-river-wash px-3 py-2 break-words">{t.text}</p>
          ) : t.role === "error" ? (
            <p key={i} role="alert" className="border-l-2 border-seal pl-3 text-seal">{t.text}</p>
          ) : (
            <article key={i} className="min-w-0 space-y-3 border-l-2 border-river pl-4">
              <Markdown text={t.reply.answer} />
              {t.reply.drafts.map((d) => (
                <LeaveSlip key={d.draft_id} id={d.draft_id} mode="draft" employee={name} leaveName={d.leave_name}
                  start={d.start} end={d.end} hoursValue={d.hours} approver={d.approver} warnings={d.warnings}
                  balance={d.balance_before !== undefined && d.balance_after !== undefined ? { before: d.balance_before, after: d.balance_after } : undefined} />
              ))}
              {t.reply.citations.length > 0 && (
                <ul className="flex flex-wrap gap-2 text-xs">
                  {t.reply.citations.map((c) => (
                    <li key={c.section} className="rounded border border-rule bg-sheet px-2 py-1 text-muted">
                      出處：{c.section.split(" > ").slice(1).join(" ")}（v{c.version}）
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-muted">
                {t.reply.meta.tools.map((x) => TOOL_LABEL[x.name] ?? x.name).join("、") || "未查詢資料"}
                {" · "}
                <span className="num">{(t.reply.meta.latency_ms / 1000).toFixed(1)}s</span>
                {!t.reply.meta.grounding_ok && " · 部分數字未能核對"}
              </p>
            </article>
          ),
        )}
        {busy && <p className="animate-pulse pl-4 text-sm text-muted motion-reduce:animate-none">查詢中…</p>}
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="sticky bottom-16 mt-6 flex gap-2 bg-paper py-3 md:bottom-0">
        <label htmlFor="ask" className="sr-only">輸入問題</label>
        <textarea id="ask" rows={1} value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="例如：幫我請下週一的特休"
          className="min-h-11 min-w-0 flex-1 resize-none rounded-md border border-rule bg-sheet px-3 py-2.5 focus:border-river focus:outline-none" />
        <button disabled={busy || !input.trim()} className="shrink-0 rounded-md bg-river px-4 text-white hover:bg-river-deep disabled:opacity-40">送出</button>
      </form>
    </section>
  );
}
