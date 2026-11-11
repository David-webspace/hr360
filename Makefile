.PHONY: setup up down logs seed kb check token eval test

setup:            ## 產生 .env（自動填密碼與金鑰，只問模型設定）
	./setup.sh

up:               ## 建置並啟動全部服務
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api web

seed:             ## 重建示範資料（不動知識庫）
	docker compose exec api python -m seed.run

kb:               ## 重新匯入規章知識庫（改了 api/kb/*.md 之後）
	docker compose exec api python -m app.kb.ingest

check:            ## 服務健康檢查＋模型連線自檢
	@curl -sf http://127.0.0.1:$${API_PORT:-8360}/health && echo " api ok"
	docker compose exec api python -m app.agent.check

token:            ## 產生 MCP 權杖：make token USER=grace.lin SCOPE=read
	docker compose exec api python -m app.tokens create $(USER) --scope $(or $(SCOPE),read)

eval:             ## 用目前設定的模型跑評測並更新模型分流表（會呼叫模型、產生費用）
	docker compose exec api python -m app.evals.run --models fast,strong --repeats 2 --write-router

test:             ## 後端測試（需要 docker compose 的資料庫在跑）
	cd api && uv run pytest -q
