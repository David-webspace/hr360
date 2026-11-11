#!/bin/sh
set -e

alembic upgrade head

if [ "${SEED_ON_START:-true}" = "true" ]; then
  python - <<'EOF'
import subprocess, sys
from sqlalchemy import text
from app.db import engine

with engine.connect() as c:
    empty = c.execute(text("SELECT NOT EXISTS (SELECT 1 FROM employees)")).scalar()
    no_kb = c.execute(text("SELECT NOT EXISTS (SELECT 1 FROM policy_chunks)")).scalar()
if empty:
    subprocess.run([sys.executable, "-m", "seed.run"], check=True)
if no_kb:
    subprocess.run([sys.executable, "-m", "app.kb.ingest"], check=True)
EOF
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
