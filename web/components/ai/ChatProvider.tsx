"use client";

import { createContext, use, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { shrinkImage } from "@/lib/image";
import type { AttachmentRef, ChatReply, Citation, ConversationSummary, Draft, ExportFile, HistoryMessage, Me, ToolUse } from "@/lib/types";

export type Turn =
  | { role: "user"; text: string; images: string[] }
  | { role: "assistant"; text: string; drafts: Draft[]; citations: Citation[]; tools: ToolUse[]; latencyMs?: number; groundingOk: boolean; suggestions?: string[]; exports: ExportFile[] }
  | { role: "error"; text: string };

type ChatState = {
  me: Me | null;
  open: boolean;
  setOpen: (open: boolean) => void;
  turns: Turn[];
  busy: boolean;
  busyText: string;
  conversationId: number | null;
  conversations: ConversationSummary[];
  available: boolean;
  floating: boolean;
  setFloating: (value: boolean) => void;
  send: (text: string, files?: File[]) => Promise<void>;
  ask: (text: string) => void;
  newConversation: () => void;
  loadConversation: (id: number) => Promise<void>;
};

const ChatContext = createContext<ChatState | null>(null);
// 只記「面板開或關」這種介面偏好；對話內容含薪資等機密，不放在瀏覽器儲存空間
const OPEN_KEY = "hr360.ai-panel-open";
const FLOAT_KEY = "hr360.ai-panel-floating";

function remember(key: string, value: boolean) {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // 無痕模式或封鎖儲存空間時只是不記住偏好
  }
}
const DOC_PROMPT = "請依我上傳的文件幫我請假";
const imageUrl = (id: string) => `/api/attachments/${id}`;

function toTurns(messages: HistoryMessage[]): Turn[] {
  return messages.map((m) =>
    m.role === "user"
      ? { role: "user", text: m.text, images: (m.meta?.attachments ?? []).map((a) => imageUrl(a.id)) }
      : {
          role: "assistant", text: m.text, drafts: m.meta?.drafts ?? [], citations: m.meta?.citations ?? [],
          tools: m.meta?.tools ?? [], latencyMs: m.meta?.latency_ms, groundingOk: m.meta?.grounding_ok ?? true,
          exports: m.meta?.exports ?? [],
        },
  );
}

async function upload(file: File): Promise<AttachmentRef | string> {
  const body = await shrinkImage(file).catch(() => null);
  if (!body) return `「${file.name}」不是可讀取的圖片`;
  const res = await fetch(`/api/attachments?name=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "content-type": "image/jpeg" }, body,
  }).catch(() => null);
  if (!res) return "上傳失敗，請檢查網路後再試一次";
  if (!res.ok) return ((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "上傳失敗";
  return (await res.json()) as AttachmentRef;
}

async function getJson<T>(path: string): Promise<T | null> {
  const res = await fetch(path).catch(() => null);
  return res && res.ok ? ((await res.json()) as T) : null;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [open, setOpenState] = useState(false);
  const [floating, setFloatingState] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyText, setBusyText] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const loaded = useRef(false);

  // 身分載入前不顯示助理；系統管理員也有助理，但後端只給它稽核統計與匯出工具
  const available = me !== null;

  const setOpen = useCallback((value: boolean) => {
    setOpenState(value);
    remember(OPEN_KEY, value);
  }, []);

  const setFloating = useCallback((value: boolean) => {
    setFloatingState(value);
    remember(FLOAT_KEY, value);
  }, []);

  const refreshList = useCallback(async () => {
    const list = await getJson<ConversationSummary[]>("/api/conversations");
    if (list) setConversations(list);
    return list ?? [];
  }, []);

  const loadConversation = useCallback(async (id: number) => {
    const messages = await getJson<HistoryMessage[]>(`/api/conversations/${id}/messages`);
    if (!messages) return;
    setConversationId(id);
    setTurns(toTurns(messages));
  }, []);

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    void (async () => {
      setMe(await getJson<Me>("/api/me"));
      try {
        // 只在寬螢幕自動重開（面板與內容並排）；手機上全螢幕會蓋住剛打開的頁面，等使用者自己點
        if (localStorage.getItem(OPEN_KEY) === "1" && window.innerWidth >= 1024) setOpenState(true);
        if (localStorage.getItem(FLOAT_KEY) === "1") setFloatingState(true);
      } catch {
        // 同上
      }
      const list = await refreshList();
      if (list.length) await loadConversation(list[0].id);
    })();
  }, [loadConversation, refreshList]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!available) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen(!open);
      } else if (e.key === "Escape" && open && (floating || window.innerWidth < 1024)) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [available, floating, open, setOpen]);

  const send = useCallback(async (text: string, files: File[] = []) => {
    const message = text.trim() || (files.length ? DOC_PROMPT : "");
    if (!message || busy) return;
    setTurns((t) => [...t, { role: "user", text: message, images: files.map((f) => URL.createObjectURL(f)) }]);
    setBusy(true);
    setBusyText(files.length ? "上傳並讀取文件中…" : "查詢中…");
    const uploaded = await Promise.all(files.map(upload));
    const failed = uploaded.find((u) => typeof u === "string");
    if (failed) {
      setBusy(false);
      setTurns((t) => [...t, { role: "error", text: failed }]);
      return;
    }
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        message, conversation_id: conversationId,
        attachment_ids: uploaded.map((u) => (u as AttachmentRef).id),
      }),
    }).catch(() => null);
    setBusy(false);
    if (!res || !res.ok) {
      const detail = res ? ((await res.json().catch(() => ({}))) as { detail?: string }).detail : undefined;
      setTurns((t) => [...t, { role: "error", text: detail ?? "連不上 HR 助理，請檢查網路後再試一次" }]);
      return;
    }
    const r = (await res.json()) as ChatReply;
    setConversationId(r.conversation_id);
    setTurns((t) => [...t, {
      role: "assistant", text: r.answer, drafts: r.drafts, citations: r.citations, tools: r.meta.tools,
      latencyMs: r.meta.latency_ms, groundingOk: r.meta.grounding_ok, suggestions: r.suggestions, exports: r.exports,
    }]);
    void refreshList();
  }, [busy, conversationId, refreshList]);

  const ask = useCallback((text: string) => {
    setOpen(true);
    void send(text);
  }, [send, setOpen]);

  const newConversation = useCallback(() => {
    setConversationId(null);
    setTurns([]);
  }, []);

  return (
    <ChatContext value={{ me, open, setOpen, turns, busy, busyText, conversationId, conversations, available, floating, setFloating, send, ask, newConversation, loadConversation }}>
      {children}
    </ChatContext>
  );
}

export function useChat(): ChatState {
  const ctx = use(ChatContext);
  if (!ctx) throw new Error("useChat 必須在 ChatProvider 內使用");
  return ctx;
}
