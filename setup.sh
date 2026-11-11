#!/usr/bin/env bash
# 產生 .env：自動填好資料庫密碼、JWT 金鑰、示範帳號密碼，只問模型設定。
# 非互動用法：LLM_PROVIDER=anthropic LLM_API_KEY=sk-... ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env && "${1:-}" != "--force" ]]; then
  echo ".env 已存在，不覆寫（要重新產生請加 --force）。"
  exit 0
fi

rand() { openssl rand -hex "$1" 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex($1))"; }

set_kv() {  # set_kv KEY VALUE：取代 .env 中 KEY= 那一行
  local key="$1" value="$2" tmp
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' .env > "$tmp"
  mv "$tmp" .env
}

ask() {  # ask 變數名 提示 預設值：已有環境變數就直接用；非互動環境用預設值
  local name="$1" prompt="$2" default="${3:-}" value="${!1:-}"
  if [[ -z "$value" && -t 0 ]]; then
    read -r -p "$prompt${default:+ [$default]}: " value
  fi
  printf -v "$name" '%s' "${value:-$default}"
}

ask_secret() {  # 同 ask，但輸入不顯示在畫面上，避免旁人或螢幕錄影看到金鑰
  local name="$1" prompt="$2" value="${!1:-}"
  if [[ -z "$value" && -t 0 ]]; then
    read -r -s -p "$prompt（輸入時不會顯示）: " value
    echo
  fi
  printf -v "$name" '%s' "$value"
}

cp .env.example .env
PG="$(rand 16)"
set_kv POSTGRES_PASSWORD "$PG"
set_kv JWT_SECRET "$(rand 32)"
DEMO="$(rand 6)"
set_kv SEED_DEMO_PASSWORD "$DEMO"
set_kv DATABASE_URL "postgresql+psycopg://hr360:${PG}@localhost:5433/hr360"

echo "要接哪一種模型？ 1) Claude 官方 API  2) Microsoft Foundry 上的 Claude  3) OpenAI 相容端點（Azure OpenAI、vLLM、Ollama…）  4) 先不設定"
ask CHOICE "請選擇" "4"
case "$CHOICE" in
  1|anthropic)
    set_kv LLM_PROVIDER anthropic
    ask_secret LLM_API_KEY "Anthropic API key"
    set_kv LLM_API_KEY "$LLM_API_KEY" ;;
  2|foundry)
    set_kv LLM_PROVIDER foundry
    ask LLM_FOUNDRY_RESOURCE "Foundry 資源名稱" ""
    ask_secret LLM_API_KEY "Foundry API key"
    ask LLM_MODEL_FAST "快速模型的部署名稱" "claude-haiku-5-5"
    ask LLM_MODEL_STRONG "強模型的部署名稱" "claude-sonnet-5-5"
    for k in LLM_FOUNDRY_RESOURCE LLM_API_KEY LLM_MODEL_FAST LLM_MODEL_STRONG; do set_kv "$k" "${!k}"; done ;;
  3|openai_compatible)
    set_kv LLM_PROVIDER openai_compatible
    ask LLM_BASE_URL "端點（例如 https://<resource>.openai.azure.com/openai/v1/ 或 http://host.docker.internal:11434/v1）" ""
    ask_secret LLM_API_KEY "API key（本機模型可留空）"
    ask LLM_MODEL_FAST "快速模型名稱" ""
    ask LLM_MODEL_STRONG "強模型名稱" "$LLM_MODEL_FAST"
    for k in LLM_BASE_URL LLM_API_KEY LLM_MODEL_FAST LLM_MODEL_STRONG; do set_kv "$k" "${!k}"; done ;;
  *) echo "先不設定模型：系統照常啟動，HR 助理聊天會提示尚未設定。之後編輯 .env 的 LLM_* 再重啟即可。" ;;
esac

cat <<EOF

完成。接下來：
  docker compose up -d --build
  開啟 http://localhost:3000 ，示範帳號例如 grace.lin（員工）、kevin.chen（主管）、sysadmin（稽核）
  示範帳號密碼：$DEMO（也記在 .env 的 SEED_DEMO_PASSWORD）
EOF
