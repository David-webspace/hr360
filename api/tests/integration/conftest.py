"""整合測試直接打已灌好示範資料的資料庫；每個測試包在交易裡，結束時回滾，不留痕跡。"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import load_principal
from app.db import engine


@pytest.fixture
def db():
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer.rollback()
    conn.close()


@pytest.fixture
def as_user(db):
    def make(username: str, channel: str = "web"):
        uid = db.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).scalar_one()
        return load_principal(db, uid, channel)
    return make
