import { Suspense } from "react";
import { AiFab, AiTopBar } from "@/components/ai/AiButtons";
import { AiPanel } from "@/components/ai/AiPanel";
import { ChatProvider } from "@/components/ai/ChatProvider";
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

// 聊天狀態放在所有頁面共用的外框：換頁時這一層不會重新掛載，對話與進行中的請求都會保留
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <ChatProvider>
      <div className="flex min-h-dvh">
        <Suspense fallback={<NavSkeleton />}>
          <UserNav />
        </Suspense>
        <div className="flex min-w-0 flex-1 flex-col">
          <AiTopBar />
          <main className="mx-auto w-full max-w-5xl min-w-0 flex-1 px-4 pt-6 pb-24 md:px-8 md:pt-0 md:pb-8">{children}</main>
        </div>
        <AiPanel />
      </div>
      <AiFab />
    </ChatProvider>
  );
}
