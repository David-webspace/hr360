import Link from "next/link";
import { Suspense } from "react";
import { Chat } from "@/components/Chat";
import { apiGet } from "@/lib/api";
import { hours } from "@/lib/format";
import type { Balance, Me } from "@/lib/types";

function suggestionsFor(me: Me): string[] {
  const base = ["我今年還剩多少特休？", "我上個月加班費怎麼算？", "幫我請下週一的特休", "育嬰留停要準備什麼？"];
  if (me.is_manager) base.splice(2, 0, "我的團隊這一季誰請最多假？");
  return base;
}

async function ChatForUser() {
  const me = await apiGet<Me>("/api/me");
  return <Chat name={me.name} suggestions={suggestionsFor(me)} />;
}

async function QuickLedger() {
  const b = await apiGet<Balance>("/api/leave/balance");
  const rows: [string, number][] = [
    ["特休可用", b.annual.available_total],
    ["補休可用", b.comp_time.available],
    ["病假全薪剩", b.statutory.sick_unhospitalized.full_pay_remaining],
  ];
  if (b.birthday && !b.birthday.expired) rows.push(["生日假", b.birthday.available]);
  return (
    <div className="rounded-md border border-rule bg-sheet">
      <p className="border-b border-rule px-4 py-2 font-display text-lg">假勤速覽</p>
      <dl className="divide-y divide-rule text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-2 px-4 py-2">
            <dt className="text-muted">{k}</dt>
            <dd className="num">{hours(v)}</dd>
          </div>
        ))}
      </dl>
      <Link href="/leave" className="block border-t border-rule px-4 py-2 text-sm text-river hover:underline">看完整帳本</Link>
    </div>
  );
}

export default function Page() {
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_15rem]">
      <Suspense fallback={<p className="text-muted">載入中…</p>}>
        <ChatForUser />
      </Suspense>
      <aside className="hidden lg:block">
        <div className="sticky top-6">
          <Suspense fallback={<div className="h-48 animate-pulse rounded-md bg-rule/40 motion-reduce:animate-none" />}>
            <QuickLedger />
          </Suspense>
        </div>
      </aside>
    </div>
  );
}
