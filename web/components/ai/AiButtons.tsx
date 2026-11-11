"use client";

import { useChat } from "@/components/ai/ChatProvider";
import { Sparkle } from "@/components/ai/Sparkle";

// 桌機固定模式：內容區右上角的膠囊按鈕；面板開著或浮動模式時隱藏（浮動模式改用右下角圓鈕）
export function AiTopBar() {
  const { open, setOpen, available, floating } = useChat();
  return (
    <div className="hidden h-14 shrink-0 items-center justify-end px-8 md:flex">
      {available && !open && !floating && (
        <button onClick={() => setOpen(true)} title="Ctrl／⌘ + J"
          className="flex items-center gap-2 rounded-full bg-river px-4 py-2 text-sm text-white shadow-sm hover:bg-river-deep">
          <Sparkle />
          問 HR 助理
        </button>
      )}
    </div>
  );
}

// 手機：底部分頁列上方的圓形按鈕；桌機浮動模式：右下角的聊天室入口
export function AiFab() {
  const { open, setOpen, busy, available, floating } = useChat();
  if (open || !available) return null;
  return (
    <button onClick={() => setOpen(true)} aria-label="問 HR 助理" title="Ctrl／⌘ + J"
      className={`fixed right-4 bottom-20 z-30 grid size-14 place-items-center rounded-full bg-river text-white shadow-lg ${floating ? "md:right-6 md:bottom-6" : "md:hidden"}`}>
      <Sparkle className="size-6" />
      {busy && <span className="absolute top-1 right-1 size-3 animate-pulse rounded-full bg-glow motion-reduce:animate-none" />}
    </button>
  );
}

export function AskChips({ prompts }: { prompts: string[] }) {
  const { ask, busy } = useChat();
  return (
    <div className="flex flex-wrap gap-2">
      {prompts.map((q) => (
        <button key={q} onClick={() => ask(q)} disabled={busy}
          className="flex items-center gap-1.5 rounded-full border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-river hover:text-river disabled:opacity-50">
          <Sparkle className="size-3.5" />
          {q}
        </button>
      ))}
    </div>
  );
}
