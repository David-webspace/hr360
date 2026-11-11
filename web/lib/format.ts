const WEEK = "日一二三四五六";

export function hours(h: number): string {
  return `${Number.isInteger(h) ? h : h.toFixed(1)} 小時`;
}

export function money(n: number): string {
  return n.toLocaleString("zh-TW");
}

function parts(iso: string) {
  const d = new Date(iso);
  const tz = new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    weekday: "short",
  }).formatToParts(d);
  const get = (t: string) => tz.find((p) => p.type === t)?.value ?? "";
  const day = new Date(d.toLocaleString("en-US", { timeZone: "Asia/Taipei" })).getDay();
  return { md: `${get("month")}/${get("day")}`, w: WEEK[day], hm: `${get("hour")}:${get("minute")}` };
}

export function span(start: string, end: string): string {
  const a = parts(start);
  const b = parts(end);
  if (a.md === b.md) return `${a.md}（${a.w}）${a.hm}–${b.hm}`;
  return `${a.md}（${a.w}）${a.hm} – ${b.md}（${b.w}）${b.hm}`;
}

export const STATUS: Record<string, { label: string; tone: string }> = {
  draft: { label: "草稿", tone: "bg-paper text-muted border-rule" },
  pending: { label: "待主管簽核", tone: "bg-glow-wash text-ink border-glow" },
  approved: { label: "已核准", tone: "bg-river-wash text-river-deep border-river" },
  rejected: { label: "已退回", tone: "bg-sheet text-seal border-seal" },
  cancelled: { label: "已取消", tone: "bg-paper text-muted border-rule" },
};
