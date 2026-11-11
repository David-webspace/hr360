import { Suspense } from "react";
import { LlmCheck } from "@/components/LlmCheck";
import { apiGet } from "@/lib/api";

type Summary = { model: string; n: number; avg_input: number; avg_output: number; avg_latency_ms: number; cost_usd: string | null; denied: number; ungrounded: number };
type Event = {
  ts: string; username: string | null; event: string; question: string | null; intent: string | null; model: string | null;
  routed_by: string | null; denied: boolean; deny_reason: string | null; input_tokens: number; output_tokens: number;
  cache_read_tokens: number; latency_ms: number | null; cost_usd: string | null; grounding_ok: boolean | null;
};

async function Audit() {
  const { summary, events } = await apiGet<{ summary: Summary[]; events: Event[] }>("/api/admin/audit");
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
        <h2 className="mb-3 font-display text-xl">最近 200 筆稽核紀錄</h2>
        <div className="overflow-x-auto rounded-md border border-rule bg-sheet">
          <table className="w-full min-w-[56rem] text-sm">
            <thead className="bg-paper text-left text-muted">
              <tr>{["時間", "帳號", "事件", "問題", "意圖／模型", "tokens 入/快取/出", "延遲", "結果"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {events.map((e, i) => (
                <tr key={i} className={e.denied ? "bg-seal/5" : undefined}>
                  <td className="num px-3 py-2 whitespace-nowrap text-muted">{new Date(e.ts).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })}</td>
                  <td className="px-3 py-2">{e.username ?? "—"}</td>
                  <td className="px-3 py-2">{e.event}</td>
                  <td className="max-w-64 truncate px-3 py-2" title={e.question ?? ""}>{e.question ?? ""}</td>
                  <td className="px-3 py-2 text-xs">{e.intent}<br /><span className="text-muted">{e.model} {e.routed_by}</span></td>
                  <td className="num px-3 py-2 text-xs">{e.input_tokens}/{e.cache_read_tokens}/{e.output_tokens}</td>
                  <td className="num px-3 py-2 text-xs">{e.latency_ms ? `${(e.latency_ms / 1000).toFixed(1)}s` : ""}</td>
                  <td className="px-3 py-2 text-xs">
                    {e.denied && <span className="text-seal">拒絕：{e.deny_reason}</span>}
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

export default function AdminPage() {
  return (
    <>
      <h1 className="font-display text-2xl">稽核與模型</h1>
      <p className="mt-1 mb-6 text-sm text-muted">系統管理員看得到用量與紀錄，看不到任何員工的人事資料。</p>
      <LlmCheck />
      <Suspense fallback={<p className="mt-6 text-muted">讀取稽核紀錄…</p>}>
        <Audit />
      </Suspense>
    </>
  );
}
