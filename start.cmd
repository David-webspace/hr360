@echo off
chcp 65001 >nul
rem 雙擊啟動 hr360：第一次會先產生設定（只問模型），之後建置並啟動所有服務、開啟瀏覽器
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo 找不到執行中的 Docker。請先安裝並開啟 Docker Desktop，等左下角顯示 Engine running 後再雙擊一次。
  pause
  exit /b 1
)

if not exist ".env" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
  if errorlevel 1 (
    echo 產生設定失敗。
    pause
    exit /b 1
  )
)

echo.
echo 建置並啟動服務中，第一次約需數分鐘…
docker compose up -d --build
if errorlevel 1 (
  echo 啟動失敗，請把上面的錯誤訊息提供給維護人員。
  pause
  exit /b 1
)

echo 等待服務就緒…
powershell -NoProfile -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing http://localhost:3000/login -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (
  echo 服務還沒就緒，可以稍後手動開啟 http://localhost:3000 ，或執行 docker compose logs api 查看原因。
  pause
  exit /b 1
)

for /f "tokens=1,* delims==" %%a in ('findstr /b "SEED_DEMO_PASSWORD=" .env') do set DEMO=%%b
echo.
echo 已啟動：http://localhost:3000
echo 示範帳號：grace.lin（員工）、kevin.chen（主管）、sysadmin（稽核）　密碼：%DEMO%
start "" http://localhost:3000
pause
