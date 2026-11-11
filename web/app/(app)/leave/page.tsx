import { Suspense } from "react";
import { MyRequests } from "@/components/MyRequests";
import { apiGet } from "@/lib/api";
import { hours } from "@/lib/format";
import type { Balance, LeaveRow } from "@/lib/types";

function Meter({ label, used, cap, note }: { label: string; used: number; cap: number; note: string }) {
  const pct = Math.min(100, Math.round((used / cap) * 100));
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span>{label}</span>
        <span className="num text-muted">{used} / {cap} h</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-rule/60">
        <div className={`h-full ${pct >= 85 ? "bg-seal" : "bg-river"}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-xs text-muted">{note}</p>
    </div>
  );
}

async function Ledger() {
  const [b, rows] = await Promise.all([apiGet<Balance>("/api/leave/balance"), apiGet<LeaveRow[]>("/api/leave/requests")]);
  const a = b.annual;
  return (
    <div className="space-y-8">
      <section>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-xl">特休帳本</h2>
          <p className="text-sm text-muted">{a.system}・截至 {b.as_of}</p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-rule bg-rule sm:max-w-md">
          <div className="bg-sheet p-4">
            <p className="text-sm text-muted">現在可以請</p>
            <p className="num text-3xl">{a.available_total}<span className="ml-1 text-base text-muted">h</span></p>
          </div>
          <div className="bg-sheet p-4">
            <p className="text-sm text-muted">剩餘（含待簽核）</p>
            <p className="num text-3xl text-muted">{a.remaining_total}<span className="ml-1 text-base">h</span></p>
          </div>
        </div>
        {a.note && <p className="mt-3 text-sm text-muted">{a.note}</p>}
        {a.periods.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-md border border-rule bg-sheet">
            <table className="w-full min-w-[34rem] text-sm">
              <thead className="bg-paper text-left text-muted">
                <tr>{["年度", "給假", "已休", "待簽核", "剩餘", "可用", "到期"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr>
              </thead>
              <tbody className="num divide-y divide-rule">
                {a.periods.map((p) => (
                  <tr key={p.period}>
                    <td className="px-3 py-2 font-sans">{p.period}</td>
                    <td className="px-3 py-2">{p.granted}</td>
                    <td className="px-3 py-2">{p.used}</td>
                    <td className="px-3 py-2">{p.pending_hold}</td>
                    <td className="px-3 py-2">{p.remaining}</td>
                    <td className="px-3 py-2 font-medium text-river">{p.available}</td>
                    <td className="px-3 py-2 text-muted">{p.expires}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-river">今年 {hours(a.entitlement_this_year.hours)} 是怎麼算的</summary>
          <ol className="mt-2 space-y-1 border-l-2 border-rule pl-3 text-muted">
            {a.entitlement_this_year.steps.map((s) => <li key={s} className="break-words">{s}</li>)}
          </ol>
        </details>
      </section>

      <section className="grid gap-6 sm:grid-cols-2">
        <Meter label="病假（未住院）" used={b.statutory.sick_unhospitalized.used} cap={b.statutory.sick_unhospitalized.cap}
          note={`全薪額度還剩 ${hours(b.statutory.sick_unhospitalized.full_pay_remaining)}，之後半薪`} />
        <Meter label="事假（含家庭照顧假）" used={b.statutory.personal_incl_family_care.used} cap={b.statutory.personal_incl_family_care.cap}
          note="事假不給薪；家庭照顧假不影響全勤" />
        <div className="text-sm">
          <p>補休可用 <span className="num">{hours(b.comp_time.available)}</span></p>
          {b.comp_time.items.map((c) => (
            <p key={c.overtime_date} className="text-xs text-muted">{c.overtime_date} 加班・{hours(c.available)}・{c.expires} 到期</p>
          ))}
        </div>
        {b.birthday && (
          <p className="text-sm">
            生日假 {b.birthday.expired ? <span className="text-muted">今年已過期</span> : <span className="num">{hours(b.birthday.available)}</span>}
            <span className="block text-xs text-muted">{b.birthday.expired ? "生日假逾期失效，不折發工資" : `可在 ${b.birthday.window} 請`}</span>
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-3 font-display text-xl">我的假單</h2>
        <MyRequests rows={rows} today={b.as_of} />
      </section>
    </div>
  );
}

export default function LeavePage() {
  return (
    <>
      <h1 className="mb-6 font-display text-2xl">假勤</h1>
      <Suspense fallback={<p className="text-muted">讀取帳本…</p>}>
        <Ledger />
      </Suspense>
    </>
  );
}
