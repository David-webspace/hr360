import { Suspense } from "react";
import { Brand, Nav } from "@/components/Nav";
import { apiGet } from "@/lib/api";
import type { Me } from "@/lib/types";

async function UserNav() {
  const me = await apiGet<Me>("/api/me");
  return <Nav me={me} />;
}

function NavSkeleton() {
  return (
    <aside className="hidden h-dvh w-48 shrink-0 flex-col gap-6 border-r border-rule px-4 py-6 md:flex">
      <Brand />
      <div className="h-40 animate-pulse rounded bg-rule/40 motion-reduce:animate-none" />
    </aside>
  );
}

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-6xl">
      <Suspense fallback={<NavSkeleton />}>
        <UserNav />
      </Suspense>
      <main className="min-w-0 flex-1 px-4 pt-6 pb-24 md:px-8 md:pb-6">{children}</main>
    </div>
  );
}
