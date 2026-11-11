"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { Me } from "@/lib/types";

type Item = { href: string; label: string };

export function navItems(me: Me): Item[] {
  if (me.roles.includes("sysadmin") && !me.emp_no) {
    return [{ href: "/admin", label: "稽核" }, { href: "/tickets", label: "工單" }];
  }
  const items: Item[] = [
    { href: "/", label: "助理" },
    { href: "/leave", label: "假勤" },
    { href: "/payslip", label: "薪資" },
  ];
  if (me.is_manager) items.push({ href: "/approvals", label: "簽核" });
  items.push({ href: "/tickets", label: "工單" });
  return items;
}

export function Brand() {
  return (
    <div>
      <p className="font-display text-2xl tracking-widest text-river">曜川</p>
      <p className="text-xs text-muted">人事服務台</p>
    </div>
  );
}

export function Nav({ me }: { me: Me }) {
  const path = usePathname();
  const router = useRouter();
  const items = navItems(me);
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-48 shrink-0 flex-col gap-6 border-r border-rule px-4 py-6 md:flex">
      <Brand />
      <nav aria-label="主選單" className="flex flex-1 flex-col gap-1">
        {items.map((it) => (
          <Link key={it.href} href={it.href} aria-current={active(it.href) ? "page" : undefined}
            className={`rounded px-3 py-2 font-display text-lg tracking-wider ${active(it.href) ? "bg-river text-white" : "text-ink hover:bg-river-wash"}`}>
            {it.label}
          </Link>
        ))}
        <div className="mt-auto border-t border-rule pt-3 text-sm">
          <p className="font-medium break-words">{me.name}</p>
          <p className="text-xs break-words text-muted">{me.unit ?? "系統帳號"}{me.title ? `・${me.title}` : ""}</p>
          <div className="mt-2 flex gap-3 text-xs">
            <Link href="/tokens" className="text-river hover:underline">連接 AI 工具</Link>
            <button onClick={logout} className="text-river hover:underline">登出</button>
          </div>
        </div>
      </nav>
      </aside>
      <nav aria-label="主選單" className="fixed inset-x-0 bottom-0 z-20 flex border-t border-rule bg-sheet md:hidden">
        {items.map((it) => (
          <Link key={it.href} href={it.href} aria-current={active(it.href) ? "page" : undefined}
            className={`flex-1 py-3 text-center font-display text-base ${active(it.href) ? "text-river" : "text-muted"}`}>
            {it.label}
          </Link>
        ))}
        <button onClick={logout} className="px-3 text-xs text-muted">登出</button>
      </nav>
    </>
  );
}
