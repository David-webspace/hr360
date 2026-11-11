export type Me = {
  username: string;
  name: string;
  roles: string[];
  is_manager: boolean;
  is_hr: boolean;
  emp_no?: string;
  unit?: string;
  title?: string;
};

export type AttachmentRef = { id: string; name: string };
export type DocumentNote = { id?: string; name?: string; summary: string; warnings?: string[] };

export type Draft = {
  draft_id: number;
  employee?: string;
  leave_type: string;
  leave_name: string;
  start: string;
  end: string;
  hours: number;
  approver: string | null;
  warnings: string[];
  status: string;
  balance_before?: number;
  balance_after?: number;
  attachments?: DocumentNote[];
};

export type Citation = { source: string; section: string; version: string };

export type ToolUse = { name: string; denied: boolean; error: boolean };

// 對話紀錄還原用：meta 只在助理回覆上有
export type HistoryMessage = {
  role: "user" | "assistant";
  text: string;
  meta: {
    drafts?: Draft[];
    citations?: Citation[];
    tools?: ToolUse[];
    grounding_ok?: boolean;
    latency_ms?: number;
    attachments?: AttachmentRef[];
  } | null;
};

export type ConversationSummary = { id: number; title: string | null; last_at: string };

export type ChatReply = {
  conversation_id: number;
  answer: string;
  drafts: Draft[];
  citations: Citation[];
  meta: {
    intent: string;
    model: string;
    routed_by: string;
    grounding_ok: boolean;
    latency_ms: number;
    cost_usd: number | null;
    tools: { name: string; denied: boolean; error: boolean }[];
  };
};

export type Period = {
  period: string;
  granted: number;
  used: number;
  pending_hold: number;
  remaining: number;
  available: number;
  expires: string;
};

export type Balance = {
  employee: string;
  as_of: string;
  annual: {
    system: string;
    periods: Period[];
    remaining_total: number;
    available_total: number;
    note?: string;
    entitlement_this_year: { hours: number; steps: string[] };
  };
  comp_time: { available: number; items: { overtime_date: string; available: number; expires: string }[] };
  birthday?: { available: number; window: string; expired: boolean };
  statutory: {
    sick_unhospitalized: { used: number; cap: number; remaining: number; full_pay_remaining: number };
    personal_incl_family_care: { used: number; cap: number; remaining: number };
  };
  marriage?: { registered: string; entitled_days: number; used_hours: number; remaining_hours: number };
};

export type LeaveRow = {
  id: number;
  employee: string;
  leave_type: string;
  leave_name: string;
  start_at: string;
  end_at: string;
  hours: number;
  status: "draft" | "pending" | "approved" | "rejected" | "cancelled";
  reason: string | null;
  created_at: string;
  attachments?: DocumentNote[];
};

export type PayslipMonth = { pay_month: string; net: number; paid_on: string };

export type Payslip = {
  employee: string;
  month: string;
  paid_on?: string;
  gross?: number;
  deductions?: number;
  net?: number;
  result?: string;
  items?: { type: "給付" | "扣款"; label: string; amount: number; steps?: string[] }[];
};

export type Ticket = {
  id: number;
  category: string;
  summary: string;
  status: string;
  confidential: boolean;
  created_at: string;
  requester: string;
};
