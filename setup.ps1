# Windows 版：產生 .env（自動填好密碼與金鑰，只問模型設定）。
# 一般直接雙擊 start.cmd 即可；單獨執行：powershell -ExecutionPolicy Bypass -File .\setup.ps1 [-Force]
param([switch]$Force)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ((Test-Path .env) -and -not $Force) { Write-Host ".env 已存在，不覆寫（要重新產生請加 -Force）。"; exit 0 }

function Rand([int]$bytes) {
  $b = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  -join ($b | ForEach-Object { $_.ToString("x2") })
}

$lines = Get-Content .env.example -Encoding UTF8
function SetKv([string]$key, [string]$value) {
  $script:lines = $script:lines | ForEach-Object { if ($_ -like "$key=*") { "$key=$value" } else { $_ } }
}

$pg = Rand 16; $demo = Rand 6
SetKv POSTGRES_PASSWORD $pg
SetKv JWT_SECRET (Rand 32)
SetKv SEED_DEMO_PASSWORD $demo
SetKv DATABASE_URL "postgresql+psycopg://hr360:$pg@localhost:5433/hr360"

Write-Host "要接哪一種模型？ 1) Claude 官方 API  2) Microsoft Foundry 上的 Claude  3) OpenAI 相容端點  4) 先不設定"
$choice = Read-Host "請選擇 [4]"
switch ($choice) {
  "1" { SetKv LLM_PROVIDER anthropic; SetKv LLM_API_KEY (Read-Host "Anthropic API key") }
  "2" {
    SetKv LLM_PROVIDER foundry
    SetKv LLM_FOUNDRY_RESOURCE (Read-Host "Foundry 資源名稱")
    SetKv LLM_API_KEY (Read-Host "Foundry API key")
    $f = Read-Host "快速模型的部署名稱 [claude-haiku-5-5]"; if ($f) { SetKv LLM_MODEL_FAST $f }
    $s = Read-Host "強模型的部署名稱 [claude-sonnet-5-5]"; if ($s) { SetKv LLM_MODEL_STRONG $s }
  }
  "3" {
    SetKv LLM_PROVIDER openai_compatible
    SetKv LLM_BASE_URL (Read-Host "端點 URL")
    SetKv LLM_API_KEY (Read-Host "API key（本機模型可留空）")
    $f = Read-Host "快速模型名稱"; SetKv LLM_MODEL_FAST $f
    $s = Read-Host "強模型名稱 [$f]"; SetKv LLM_MODEL_STRONG ($(if ($s) { $s } else { $f }))
  }
  default { Write-Host "先不設定模型：系統照常啟動，HR 助理聊天會提示尚未設定。" }
}

# 不用 Set-Content -Encoding UTF8：Windows PowerShell 5.1 會加 BOM，Docker Compose 讀 .env 會出錯
[System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$lines, (New-Object System.Text.UTF8Encoding $false))
Write-Host "`n完成。接下來：docker compose up -d --build，開啟 http://localhost:3000"
Write-Host "示範帳號密碼：$demo（也記在 .env 的 SEED_DEMO_PASSWORD）"
