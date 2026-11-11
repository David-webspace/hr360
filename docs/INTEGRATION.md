# 接入指南：用你們自己的 AI

hr360 的正確性與權限不依賴模型：數字由計算引擎產生、權限在資料層、送出假單要本人確認。換成你們的模型時，只需要設定連線，再跑一次評測確認它的表現。

## 1. 兩種接法

| 接法 | 適合 | 說明 |
|---|---|---|
| A. 內建 HR 助理＋你們的模型 | 只有模型 API | 在 `.env` 設定模型端點；網頁聊天、分流、稽核照常使用 |
| B. MCP | 已有自己的 Agent 平台 | 你們的 Agent 透過 `/mcp` 呼叫 hr360 的 12 個工具；權限、計算、稽核仍由 hr360 負責 |

兩種可以同時使用。

## 2. 設定模型（接法 A）

執行 `./setup.sh` 會引導填寫；也可以直接編輯 `.env` 後 `docker compose up -d` 重啟 api。

`LLM_MODEL_FAST` 用於簡單查詢與意圖分類，`LLM_MODEL_STRONG` 用於分析、多步驟與數字檢查不通過時的重答；兩者可以設成同一個模型。

### Claude 官方 API

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL_FAST=claude-haiku-5-5
LLM_MODEL_STRONG=claude-sonnet-5-5
```

### Microsoft Foundry 上的 Claude

```env
LLM_PROVIDER=foundry
LLM_FOUNDRY_RESOURCE=<資源名稱>
LLM_API_KEY=<Foundry 金鑰>
LLM_MODEL_FAST=<Haiku 的部署名稱>
LLM_MODEL_STRONG=<Sonnet 的部署名稱>
```

使用官方 `AnthropicFoundry` client。若你們的端點不是標準資源網址，改填 `LLM_BASE_URL`。

### Azure OpenAI、vLLM、Ollama、LiteLLM 等 OpenAI 相容端點

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://<resource>.openai.azure.com/openai/v1/   # Azure OpenAI v1 端點
LLM_API_KEY=<金鑰>
LLM_MODEL_FAST=<部署或模型名稱>
LLM_MODEL_STRONG=<部署或模型名稱>
```

本機 Ollama（Docker 內連主機）：`LLM_BASE_URL=http://host.docker.internal:11434/v1`。推理型模型建議加 `LLM_REASONING_EFFORT=none`，否則可能把輸出額度全花在思考、回傳空白。

模型需要支援工具呼叫（function calling）。

### 成本

在 `api/config/pricing.yaml` 填入你們模型的單價（美元／百萬 tokens），稽核頁與評測報告才會計算金額；沒填只記 token 數。

## 3. 確認連線

```bash
make check
```

或用 `sysadmin` 登入網頁，在「稽核」頁按「執行自檢」。會分別測試 fast、strong 兩個模型的連線、工具呼叫與繁體中文輸出。

## 4. 評測你們的模型

```bash
make eval
```

用目前設定的模型跑完 38 題評測（每題 2 次），產生：

- `api/eval/REPORT.md`：通過率、數字正確率、口徑正確率、越權洩漏率、延遲、成本，以及未通過的題目與原因
- `api/config/router_table.yaml`：依結果決定每類問題用 fast 還是 strong

口徑由 judge 模型（`LLM_MODEL_STRONG`）判斷。換了 judge 模型請先跑 `docker compose exec api python -m app.evals.calibrate`，確認它能分辨正確回答與故意改錯的版本（全部判對才採信）。

上線建議門檻：越權洩漏率 0%、數字正確率 100%；口徑正確率不足時檢查 REPORT.md 列出的題目，通常是模型把「已扣除／未扣除」「只計已核准」這類口徑說反。

新增自己的題目：在 `api/eval/cases.yaml` 加入，寫明使用者、問題、預期數字與口徑；`--cases` 可以只跑部分題目，`--merge` 可以與上一次結果合併，不必全部重跑：

```bash
docker compose exec api python -m app.evals.run --cases L1,S1 --models fast,strong
```

## 5. MCP（接法 B）

### 產生權杖

- 網頁：左下角「連接 AI 工具」→ 產生權杖
- 指令：`make token USER=grace.lin SCOPE=read`

權杖代表該員工本人，看得到的資料和網頁相同。`read` 只能查詢；`action` 才能建立、送出假單與開立工單。給 AI 自動使用的權杖建議用 `read`。權杖只在產生時顯示一次，資料庫只存雜湊值；最長 90 天，可隨時撤銷。

### 連線設定

- 端點：`http://<主機>:8360/mcp`（Streamable HTTP）
- 標頭：`Authorization: Bearer hr360_...`

Claude Code：

```bash
claude mcp add --transport http hr360 http://localhost:8360/mcp --header "Authorization: Bearer hr360_..."
```

支援 HTTP 標頭的 MCP client 通用設定：

```json
{
  "mcpServers": {
    "hr360": {
      "type": "http",
      "url": "http://localhost:8360/mcp",
      "headers": { "Authorization": "Bearer hr360_..." }
    }
  }
}
```

工具清單：`find_employee`、`get_leave_balance`、`get_overtime_pay`、`get_team_leave_summary`、`get_salary`、`get_payslip`、`get_insurance_summary`、`get_travel_subsidy`、`search_policy`、`draft_leave_request`、`create_hr_ticket`、`submit_leave_request`。每次呼叫都記錄在稽核中（來源標示 `mcp`）。

## 6. 換成你們的資料

| 要換的 | 位置 | 做法 |
|---|---|---|
| 公司規定（福利金額、補助、加給…） | `api/app/company/policy.py` | 修改參數；`api/tests/test_kb_consistency.py` 會檢查規章文件的數字是否一致 |
| 規章文件 | `api/kb/*.md` | 依同樣格式（`---` 標頭、`##` 章、`###` 條）撰寫，執行 `make kb` 重新匯入 |
| 法規參數 | `api/app/engine/rules.py`、`calendar_tw.py` | 依生效日新增版本，同步更新 `docs/sources.md` 與測試 |
| 員工與出勤資料 | PostgreSQL | 設 `SEED_ON_START=false`、清空 `APP_TODAY`，再由 HR 系統匯入 `employees`、`org_units`、`leave_ledger` 等資料表（結構見 `api/app/models/`） |

## 7. 部署注意事項

- **對內網開放**：`.env` 設 `WEB_BIND=0.0.0.0`；API 與資料庫預設只開放本機。
- **HTTPS**：放在反向代理後，並設 `COOKIE_SECURE=true`。
- **企業網路**：建置時需要連到 Docker Hub、PyPI、npm 與 Hugging Face（下載 embedding 模型，已打包進映像檔，執行時不需要）。若有代理伺服器，設定 Docker 的 `HTTP_PROXY`／`HTTPS_PROXY`。
- **備份**：資料在 Docker volume `hr360_pgdata`。
- **多副本**：限流目前在單一程序內實作，多副本部署需改用 Redis。
