"use client";

import { useState } from "react";

// 示範帳號：讓評估者不用查文件就能切換角色體驗權限差異（密碼見部署時的 SEED_DEMO_PASSWORD）
const DEMO = [
  { u: "grace.lin", who: "林佳穎", role: "員工・軟體工程師" },
  { u: "kevin.chen", who: "陳冠宇", role: "主管・韌體一課課長" },
  { u: "vivian.wu", who: "吳欣怡", role: "HRBP・研發與製造" },
  { u: "sharon.tsai", who: "蔡淑芬", role: "薪酬人員" },
  { u: "sysadmin", who: "系統管理員", role: "只看稽核與用量" },
];

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器，請確認服務已啟動");
    if (!res.ok) return setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "登入失敗");
    const me = (await res.json()) as { roles: string[] };
    // 同登出：整頁載入，確保不沿用前一位使用者留在瀏覽器記憶體裡的狀態
    window.location.replace(me.roles.includes("sysadmin") && me.roles.length === 1 ? "/admin" : "/");
  }

  return (
    <main className="mx-auto grid min-h-dvh max-w-4xl items-center gap-10 px-4 py-10 md:grid-cols-[1fr_20rem]">
      <section className="min-w-0">
        <p className="font-display text-5xl tracking-[0.2em] text-river">曜川</p>
        <h1 className="mt-3 font-display text-3xl">人事服務台</h1>
        <p className="mt-4 max-w-md text-muted">特休還剩多少、加班費怎麼算、明天想請假——直接問。數字由系統依勞基法與公司規定計算，假單送出前一定由你本人確認。</p>
        <div className="mt-8">
          <p className="mb-2 text-sm text-muted">示範帳號（點一下帶入）</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {DEMO.map((d) => (
              <li key={d.u}>
                <button type="button" onClick={() => setUsername(d.u)}
                  className={`w-full rounded-md border px-3 py-2 text-left hover:border-river ${username === d.u ? "border-river bg-river-wash" : "border-rule bg-sheet"}`}>
                  <span className="block font-medium">{d.who}</span>
                  <span className="block text-xs text-muted">{d.role}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <form onSubmit={submit} className="rounded-md border border-rule bg-sheet p-6">
        <h2 className="mb-4 font-display text-xl">登入</h2>
        <label className="block text-sm text-muted" htmlFor="u">帳號</label>
        <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required
          className="mt-1 mb-4 w-full rounded border border-rule px-3 py-2 focus:border-river focus:outline-none" />
        <label className="block text-sm text-muted" htmlFor="p">密碼</label>
        <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required
          className="mt-1 w-full rounded border border-rule px-3 py-2 focus:border-river focus:outline-none" />
        {error && <p role="alert" className="mt-3 text-sm text-seal">{error}</p>}
        <button disabled={busy} className="mt-6 w-full rounded bg-river py-2.5 text-white hover:bg-river-deep disabled:opacity-50">
          {busy ? "登入中…" : "登入"}
        </button>
      </form>
    </main>
  );
}
