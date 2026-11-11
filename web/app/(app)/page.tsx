import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { AskChips } from "@/components/ai/AiButtons";
import { MyRequests } from "@/components/MyRequests";
import { apiGet } from "@/lib/api";
import { hours } from "@/lib/format";
import type { Balance, LeaveRow, Me } from "@/lib/types";

const WEEK = "日一二三四五六";

function Tile({ label, value, note, tone = "text-ink" }: { label: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="min-w-0 bg-sheet p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className={`num mt-1 text-2xl ${tone}`}>{value}</p>
      {note && <p className="mt-1 text-xs break-words text-muted">{note}</p>}
    </div>
  );
}

async function Overview() {
  const me = await apiGet<Me>("/api/me");
  if (!me.emp_no) redirect("/admin");
  const [b, rows, pending] = await Promise.all([
    apiGet<Balance>("/api/leave/balance"),
    apiGet<LeaveRow[]>("/api/leave/requests"),
    me.is_manager ? apiGet<LeaveRow[]>("/api/approvals") : Promise.resolve([] as LeaveRow[]),
  ]);
  const d = new Date(`${b.as_of}T12:00:00Z`); // 取當日中午 UTC 再用 getUTCDay，不受伺服器時區影響
  const recent = rows.filter((r) => r.status !== "cancelled" && r.status !== "draft").slice(0, 5);
  const sick = b.statutory.sick_unhospitalized;
  const prompts = ["我今年還剩多少特休？", "我上個月加班費怎麼算？", "幫我請下週一的特休"];
  if (me.is_manager) prompts.push("我的團隊這一季誰請最多假？");

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm text-muted">{b.as_of.replaceAll("-", "/")}（{WEEK[d.getUTCDay()]}）</p>
        <h1 className="mt-1 font-display text-3xl break-words">{me.name}，你好</h1>
        <p className="mt-1 text-sm break-words text-muted">{me.unit}・{me.title}</p>
      </header>

      <section aria-label="假勤速覽" className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-rule bg-rule lg:grid-cols-4">
        <Tile label="特休現在可以請" value={hours(b.annual.available_total)} tone="text-river"
          note={b.annual.note ?? `剩餘 ${hours(b.annual.remaining_total)}（含待簽核）`} />
        <Tile label="補休可用" value={hours(b.comp_time.available)}
          note={b.comp_time.items[0] ? `最早 ${b.comp_time.items[0].expires} 到期` : "目前沒有補休"} />
        <Tile label="病假全薪額度" value={hours(sick.full_pay_remaining)} note={`今年已請 ${hours(sick.used)}，上限 ${hours(sick.cap)}`} />
        <Tile label="生日假" value={b.birthday && !b.birthday.expired ? hours(b.birthday.available) : "—"}
          note={b.birthday ? (b.birthday.expired ? "今年已過期" : `可在 ${b.birthday.window} 請`) : undefined} />
      </section>

      {me.is_manager && (
        <Link href="/approvals" className="flex items-center justify-between gap-3 rounded-md border border-glow bg-glow-wash px-4 py-3 hover:border-river">
          <span>待你簽核的假單</span>
          <span className="num text-xl">{pending.length} 張 →</span>
        </Link>
      )}

      <section className="rounded-md border border-rule bg-sheet p-4">
        <h2 className="font-display text-xl">問 HR 助理</h2>
        <p className="mt-1 mb-3 text-sm text-muted">點一下就會開啟助理並送出問題；換頁時對話會保留，也可以隨時按 Ctrl／⌘ + J 開關。</p>
        <AskChips prompts={prompts} />
      </section>

      <section>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="font-display text-xl">最近的假單</h2>
          <Link href="/leave" className="text-sm text-river hover:underline">看完整帳本</Link>
        </div>
        <MyRequests rows={recent} today={b.as_of} />
      </section>
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<p className="text-muted">載入中…</p>}>
      <Overview />
    </Suspense>
  );
}
