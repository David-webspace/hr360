import { Suspense } from "react";
import { TokenManager, type TokenRow } from "@/components/TokenManager";
import { apiGet } from "@/lib/api";

async function Tokens() {
  const rows = await apiGet<TokenRow[]>("/api/tokens");
  return <TokenManager rows={rows} />;
}

const CONFIG = `{
  "mcpServers": {
    "hr360": {
      "type": "http",
      "url": "http://localhost:8360/mcp",
      "headers": { "Authorization": "Bearer <你的權杖>" }
    }
  }
}`;

export default function TokensPage() {
  return (
    <>
      <h1 className="font-display text-2xl">連接 AI 工具</h1>
      <p className="mt-1 mb-6 max-w-2xl text-sm text-muted">
        用個人權杖把 hr360 接到你自己的 AI 工具（例如 Claude Desktop、公司內部 Agent）。權杖代表你本人：
        看得到的資料和網頁一樣，所有呼叫都會記錄在稽核中。給 AI 自動使用的權杖建議選「唯讀」。
      </p>
      <Suspense fallback={<p className="text-muted">讀取權杖…</p>}>
        <Tokens />
      </Suspense>
      <section className="mt-8 max-w-2xl">
        <h2 className="mb-2 font-display text-xl">MCP 設定範例</h2>
        <pre className="num overflow-x-auto rounded-md border border-rule bg-sheet p-4 text-xs">{CONFIG}</pre>
      </section>
    </>
  );
}
