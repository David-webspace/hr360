// 稽核紀錄在資料庫存代碼（穩定、好查詢），畫面顯示中文；未列入的代碼原樣顯示
export const EVENT_LABEL: Record<string, string> = {
  chat: "問答", login: "登入", login_failed: "登入失敗", attachment_upload: "上傳文件",
  leave_submit: "送出假單", leave_cancel: "取消假單", leave_approve: "核准假單", leave_reject: "駁回假單",
  mcp_tool: "MCP 工具呼叫", token_create: "建立存取權杖", token_revoke: "撤銷存取權杖",
  report_export: "匯出報表", report_download: "下載報表",
};

export const INTENT_LABEL: Record<string, string> = {
  "lookup.leave_balance": "查假勤餘額", "lookup.overtime_pay": "查加班費", "lookup.payroll": "查薪資",
  "lookup.benefits": "查福利", "analysis.team": "團隊出勤", "action.leave_request": "請假",
  "policy.qa": "規章問答", escalate: "申訴／轉人資", "report.export": "匯出報表", "audit.stats": "稽核統計", other: "其他",
};

export const DENY_LABEL: Record<string, string> = {
  out_of_scope_or_not_found: "超出權限或查無此人", ambiguous: "對象不明確（同名）", not_manager: "非主管",
  no_employee_record: "無員工資料", attachment_not_found: "文件不存在", attachment_not_owned: "非本人文件",
  leave_not_owned_or_state: "非本人假單或狀態不符", not_approver_or_state: "非簽核人或狀態不符",
  read_only_token: "唯讀權杖不可寫入", not_sysadmin: "非系統管理員", export_not_found: "檔案不存在或已過期",
};

const ROUTE_LABEL: Record<string, string> = {
  rule: "規則分類", llm: "模型分類", default: "預設", attachment: "依上傳文件", role: "依角色",
  nudge: "提醒補查", grounding_escalation: "數字未核對，改用強模型",
};

export function routeLabel(code: string | null): string {
  if (!code) return "";
  return code.split("+").map((c) => (c.startsWith("forced:") ? `指定 ${c.slice(7)}` : ROUTE_LABEL[c] ?? c)).join("・");
}

export function label(map: Record<string, string>, code: string | null): string {
  return code ? map[code] ?? code : "";
}
