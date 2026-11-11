import { Suspense } from "react";
import { LlmCheck } from "@/components/LlmCheck";
import { apiGet } from "@/lib/api";
import { DENY_LABEL, EVENT_LABEL, INTENT_LABEL, label, routeLabel } from "@/lib/auditLabels";

type Summary = { model: string; n: number; avg_input: number; avg_output: number; avg_latency_ms: number; cost_usd: string | null; denied: number; ungrounded: number };
type Event = {
  ts: string; username: string | null; name: string | null; event: string; question: string | null; intent: string | null; model: string | null;
  routed_by: string | null; denied: boolean; deny_reason: string | null; input_tokens: number; output_tokens: number;
  cache_read_tokens: number; latency_ms: number | null; cost_usd: string | null; grounding_ok: boolean | null;
};

type Params = Promise<Record<string, string | string[] | undefined>>;
const FILTERS = ["event", "user", "intent", "flagged"] as const;
const FIELD = "rounded border border-rule bg-paper px-2 py-1.5 text-sm focus:border-river focus:outline-none";

async function Audit({ searchParams }: { searchParams: Params }) {
  const sp = await searchParams;
  const f = Object.fromEntries(FILTERS.map((k) => [k, typeof sp[k] === "string" ? sp[k] : ""])) as Record<(typeof FILTERS)[number], string>;
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const { summary, events } = await apiGet<{ summary: Summary[]; events: Event[] }>(`/api/admin/audit${qs ? `?${qs}` : ""}`);
  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 font-display text-xl">模型用量</h2>
        <div className="overflow-x-auto rounded-md border border-rule bg-sheet">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="bg-paper text-left text-muted">
              <tr>{["模型", "問答數", "平均輸入", "平均輸出", "平均延遲", "總成本 USD", "拒絕", "數字未核對"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody className="num divide-y divide-rule">
              {summary.map((s) => (
                <tr key={s.model}>
                  <td className="px-3 py-2 font-sans">{s.model}</td>
                  <td className="px-3 py-2">{s.n}</td>
                  <td className="px-3 py-2">{s.avg_input}</td>
                  <td className="px-3 py-2">{s.avg_output}</td>
                  <td className="px-3 py-2">{(s.avg_latency_ms / 1000).toFixed(1)}s</td>
                  <td className="px-3 py-2">{s.cost_usd === null ? "—" : Number(s.cost_usd).toFixed(4)}</td>
                  <td className="px-3 py-2">{s.denied}</td>
                  <td className="px-3 py-2">{s.ungrounded}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h2 className="mb-3 font-display text-xl">稽核紀錄</h2>
        <form className="mb-3 flex flex-wrap items-center gap-2">
          <select name="event" defaultValue={f.event} aria-label="事件" className={FIELD}>
            <option value="">全部事件</option>
            {Object.entries(EVENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select name="intent" defaultValue={f.intent} aria-label="意圖" className={FIELD}>
            <option value="">全部意圖</option>
            {Object.entries(INTENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input name="user" defaultValue={f.user} placeholder="帳號或姓名" aria-label="帳號或姓名" maxLength={40} className={`${FIELD} w-36 min-w-0`} />
          <label className="flex items-center gap-1.5 text-sm text-muted">
            <input type="checkbox" name="flagged" value="true" defaultChecked={f.flagged === "true"} />只看拒絕與數字未核對
          </label>
          <button className="rounded bg-river px-3 py-1.5 text-sm text-white hover:bg-river-deep">篩選</button>
          {qs && <a href="/admin" className="text-sm text-river hover:underline">清除</a>}
          <span className="ml-auto text-xs text-muted">{events.length === 200 ? "顯示最新 200 筆" : `共 ${events.length} 筆`}</span>
        </form>
        <div className="overflow-x-auto rounded-md border border-rule bg-sheet">
          <table className="w-full min-w-[56rem] text-sm">
            <thead className="bg-paper text-left text-muted">
              <tr>{["時間", "使用者", "事件", "問題", "意圖／模型", "tokens 入/快取/出", "延遲", "結果"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {events.map((e, i) => (
                <tr key={i} className={e.denied ? "bg-seal/5" : undefined}>
                  <td className="num px-3 py-2 whitespace-nowrap text-muted">{new Date(e.ts).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })}</td>
                  <td className="px-3 py-2">{e.name ?? e.username ?? "—"}{e.name && <span className="block text-xs text-muted">{e.username}</span>}</td>
                  <td className="px-3 py-2 whitespace-nowrap" title={e.event}>{label(EVENT_LABEL, e.event)}</td>
                  <td className="max-w-64 truncate px-3 py-2" title={e.question ?? ""}>{e.question ?? ""}</td>
                  <td className="px-3 py-2 text-xs" title={[e.intent, e.routed_by].filter(Boolean).join(" ")}>
                    {label(INTENT_LABEL, e.intent)}
                    {e.model && <span className="block text-muted">{e.model}・{routeLabel(e.routed_by)}</span>}
                  </td>
                  <td className="num px-3 py-2 text-xs">{e.input_tokens}/{e.cache_read_tokens}/{e.output_tokens}</td>
                  <td className="num px-3 py-2 text-xs">{e.latency_ms ? `${(e.latency_ms / 1000).toFixed(1)}s` : ""}</td>
                  <td className="px-3 py-2 text-xs">
                    {e.denied && <span className="text-seal" title={e.deny_reason ?? ""}>拒絕：{label(DENY_LABEL, e.deny_reason)}</span>}
                    {e.grounding_ok === false && <span className="text-seal">數字未核對</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default function AdminPage({ searchParams }: { searchParams: Params }) {
  return (
    <>
      <h1 className="font-display text-2xl">稽核與模型</h1>
      <p className="mt-1 mb-6 text-sm text-muted">系統管理員看得到用量與紀錄，看不到任何員工的人事資料。</p>
      <LlmCheck />
      <Suspense fallback={<p className="mt-6 text-muted">讀取稽核紀錄…</p>}>
        <Audit searchParams={searchParams} />
      </Suspense>
    </>
  );
}
