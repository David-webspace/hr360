import Link from "next/link";
import { Suspense } from "react";
import { apiGet } from "@/lib/api";
import { money } from "@/lib/format";
import type { Payslip, PayslipMonth } from "@/lib/types";

async function Slip({ searchParams }: { searchParams: PageProps<"/payslip">["searchParams"] }) {
  const months = await apiGet<PayslipMonth[]>("/api/payslips");
  if (!months.length) return <p className="text-muted">還沒有薪資單。到職後第一個發薪日（每月 5 日）會出現在這裡。</p>;
  const q = (await searchParams).m;
  const month = typeof q === "string" && months.some((m) => m.pay_month === q) ? q : months[0].pay_month;
  const s = await apiGet<Payslip>(`/api/payslips/${month}`);
  const earn = s.items?.filter((i) => i.type === "給付") ?? [];
  const ded = s.items?.filter((i) => i.type === "扣款") ?? [];

  return (
    <div className="space-y-6">
      <nav aria-label="選擇月份" className="flex gap-2 overflow-x-auto pb-1">
        {months.slice(0, 12).map((m) => (
          <Link key={m.pay_month} href={`/payslip?m=${m.pay_month}`} aria-current={m.pay_month === month ? "page" : undefined}
            className={`num shrink-0 rounded border px-3 py-1 text-sm ${m.pay_month === month ? "border-river bg-river text-white" : "border-rule bg-sheet hover:border-river"}`}>
            {m.pay_month}
          </Link>
        ))}
      </nav>

      <article className="max-w-xl overflow-hidden rounded-md border border-rule bg-sheet">
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-4 py-3">
          <h2 className="font-display text-xl">{month} 薪資單</h2>
          <span className="text-sm text-muted">{s.paid_on} 發放</span>
        </header>
        {[["給付", earn], ["扣款", ded]].map(([title, list]) => (
          <section key={title as string} className="border-b border-rule px-4 py-3">
            <h3 className="mb-2 text-sm text-muted">{title as string}</h3>
            <ul className="space-y-1.5">
              {(list as NonNullable<Payslip["items"]>).map((i) => (
                <li key={i.label}>
                  <div className="flex justify-between gap-3">
                    <span className="min-w-0 break-words">{i.label}</span>
                    <span className="num">{title === "扣款" ? "−" : ""}{money(i.amount)}</span>
                  </div>
                  {i.steps && (
                    <details className="text-xs text-muted">
                      <summary className="cursor-pointer text-river">計算方式</summary>
                      <ol className="mt-1 space-y-0.5 border-l-2 border-rule pl-2">{i.steps.map((x) => <li key={x} className="break-words">{x}</li>)}</ol>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
        <footer className="flex items-baseline justify-between gap-3 px-4 py-4">
          <span className="font-display text-lg">實發</span>
          <span className="num text-2xl text-river">{money(s.net ?? 0)}</span>
        </footer>
      </article>
      <p className="text-xs text-muted">薪資資料只有本人與薪酬人員可以查看。</p>
    </div>
  );
}

export default function PayslipPage({ searchParams }: PageProps<"/payslip">) {
  return (
    <>
      <h1 className="mb-6 font-display text-2xl">薪資</h1>
      <Suspense fallback={<p className="text-muted">讀取薪資單…</p>}>
        <Slip searchParams={searchParams} />
      </Suspense>
    </>
  );
}
