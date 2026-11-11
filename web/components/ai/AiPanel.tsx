"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useChat } from "@/components/ai/ChatProvider";
import { AiReply } from "@/components/ai/AiReply";
import { Sparkle } from "@/components/ai/Sparkle";

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILES = 3;

type Pending = { file: File; url: string };

function suggestionsFor(isManager: boolean): string[] {
  const base = ["我今年還剩多少特休？", "我上個月加班費怎麼算？", "幫我請下週一的特休", "育嬰留停要準備什麼？"];
  if (isManager) base.splice(2, 0, "我的團隊這一季誰請最多假？");
  return base;
}

function Thumb({ src, alt }: { src: string; alt: string }) {
  return <Image src={src} alt={alt} width={64} height={64} unoptimized className="size-16 rounded border border-rule bg-paper object-cover" />;
}

export function AiPanel() {
  const { me, open, setOpen, turns, busy, busyText, send, conversations, conversationId, loadConversation, newConversation } = useChat();
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<Pending[]>([]);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  // 大括號不可省：新版瀏覽器的 scrollIntoView 會回傳 Promise，被 React 當成 cleanup 呼叫會整頁崩潰
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns, busy, open]);
  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);

  if (!open) return null;
  const name = me?.name ?? "";

  function add(list: FileList | File[]) {
    const images = Array.from(list).filter((f) => ACCEPT.includes(f.type));
    setNotice(images.length < Array.from(list).length ? "只接受 JPG、PNG 或 WebP 圖片" : null);
    setFiles((cur) => [...cur, ...images.map((file) => ({ file, url: URL.createObjectURL(file) }))].slice(0, MAX_FILES));
  }

  function remove(i: number) {
    setFiles((cur) => {
      URL.revokeObjectURL(cur[i].url);
      return cur.filter((_, j) => j !== i);
    });
  }

  function submit() {
    if (busy || (!input.trim() && !files.length)) return;
    const text = input;
    const picked = files.map((f) => f.file);
    files.forEach((f) => URL.revokeObjectURL(f.url));
    setInput("");
    setFiles([]);
    setNotice(null);
    void send(text, picked);
  }

  return (
    <>
      <div onClick={() => setOpen(false)} className="fixed inset-0 z-30 hidden bg-ink/20 md:block lg:hidden" aria-hidden="true" />
      <aside aria-label="HR 助理"
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }}
        onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}
        className="fixed inset-0 z-40 flex flex-col bg-paper md:left-auto md:w-[26rem] md:border-l md:border-rule md:shadow-xl lg:sticky lg:inset-auto lg:top-0 lg:z-auto lg:h-dvh lg:shrink-0 lg:shadow-none">
        {dragging && (
          <div className="pointer-events-none absolute inset-2 z-10 grid place-items-center rounded-md border-2 border-dashed border-river bg-river-wash/80 text-river">
            放開以附上證明文件
          </div>
        )}
        <header className="flex items-center gap-2 border-b border-rule bg-sheet px-4 py-3">
          <Sparkle className="size-5 text-river" />
          <h2 className="font-display text-lg">HR 助理</h2>
          <select aria-label="切換對話" value={conversationId ?? ""} disabled={busy}
            onChange={(e) => (e.target.value ? void loadConversation(Number(e.target.value)) : newConversation())}
            className="ml-auto max-w-36 min-w-0 truncate rounded border border-rule bg-sheet px-2 py-1 text-xs text-muted">
            <option value="">新對話</option>
            {conversations.map((c) => <option key={c.id} value={c.id}>{c.title ?? `對話 ${c.id}`}</option>)}
          </select>
          <button onClick={newConversation} disabled={busy} title="開新對話" className="rounded px-2 py-1 text-sm text-river hover:bg-river-wash disabled:opacity-50">＋</button>
          <button onClick={() => setOpen(false)} aria-label="關閉 HR 助理" title="關閉（Ctrl／⌘ + J）" className="rounded px-2 py-1 text-muted hover:bg-paper hover:text-ink">✕</button>
        </header>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
          {turns.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted">{name ? `${name}，` : ""}特休、加班費、薪資單、請假與公司規定都可以問。數字由系統依勞基法與公司規定計算；假單由你按確認後才會送出。</p>
              <p className="text-sm text-muted">有診斷證明、訃聞或結婚證書？拍照附上，助理會讀出日期並幫你建立假單草稿。</p>
              <div className="flex flex-wrap gap-2">
                {suggestionsFor(Boolean(me?.is_manager)).map((s) => (
                  <button key={s} onClick={() => void send(s)} className="rounded-full border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-river hover:text-river">{s}</button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="ml-auto flex w-fit max-w-[85%] flex-col items-end gap-1.5">
                {t.images.length > 0 && (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {t.images.map((src) => <Thumb key={src} src={src} alt="附上的證明文件" />)}
                  </div>
                )}
                <p className="rounded-md bg-river-wash px-3 py-2 text-sm break-words">{t.text}</p>
              </div>
            ) : t.role === "error" ? (
              <p key={i} role="alert" className="border-l-2 border-seal pl-3 text-sm text-seal">{t.text}</p>
            ) : (
              <div key={i} className="text-sm"><AiReply t={t} name={name} /></div>
            ),
          )}
          {busy && <p className="animate-pulse pl-3 text-sm text-muted motion-reduce:animate-none">{busyText}</p>}
          <div ref={end} />
        </div>

        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="border-t border-rule bg-sheet p-3">
          {(files.length > 0 || notice) && (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {files.map((f, i) => (
                <div key={f.url} className="relative">
                  <Thumb src={f.url} alt={f.file.name} />
                  <button type="button" onClick={() => remove(i)} aria-label={`移除 ${f.file.name}`}
                    className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full bg-ink text-[10px] text-paper">✕</button>
                </div>
              ))}
              {notice && <p className="text-xs text-seal">{notice}</p>}
            </div>
          )}
          <div className="flex gap-2">
            <input ref={picker} type="file" accept={ACCEPT.join(",")} multiple hidden
              onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
            <button type="button" onClick={() => picker.current?.click()} disabled={busy || files.length >= MAX_FILES}
              aria-label="附上證明文件" title="附上證明文件（診斷證明、訃聞、結婚證書）"
              className="shrink-0 self-end rounded-md border border-rule px-2.5 py-2 text-muted hover:border-river hover:text-river disabled:opacity-40">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="size-5" aria-hidden="true">
                <path d="M21 11.5 12.4 20a5 5 0 0 1-7.1-7.1l8.6-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.5a1.7 1.7 0 0 1-2.4-2.4l7.9-7.8" />
              </svg>
            </button>
            <label htmlFor="ai-ask" className="sr-only">輸入問題</label>
            <textarea id="ai-ask" ref={field} rows={2} value={input} maxLength={2000} onChange={(e) => setInput(e.target.value)}
              onPaste={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); add(e.clipboardData.files); } }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={files.length ? "可補充說明，或直接送出" : "例如：幫我請下週一的特休"}
              className="min-w-0 flex-1 resize-none rounded-md border border-rule bg-paper px-3 py-2 text-sm focus:border-river focus:outline-none" />
            <button disabled={busy || (!input.trim() && !files.length)} className="shrink-0 self-end rounded-md bg-river px-4 py-2 text-sm text-white hover:bg-river-deep disabled:opacity-40">送出</button>
          </div>
        </form>
      </aside>
    </>
  );
}
