"""規章檢索：向量相似度＋字元三元組（條號、專有名詞）混合排序。"""

from sqlalchemy import text

from app.db import engine
from app.kb.embedding import embed_query

SQL = text("""
    SELECT c.id, d.slug, d.title, d.version, c.section_path, c.text,
           1 - (c.embedding <=> CAST(:qv AS vector)) AS vec,
           word_similarity(:q, c.text) AS kw
    FROM policy_chunks c JOIN policy_documents d ON d.id = c.doc_id
    ORDER BY 0.75 * (1 - (c.embedding <=> CAST(:qv AS vector))) + 0.25 * word_similarity(:q, c.text) DESC
    LIMIT :k
""")


def search(query: str, k: int = 5) -> list[dict]:
    qv = embed_query(query)
    with engine.connect() as conn:
        rows = conn.execute(SQL, {"q": query, "qv": str(qv), "k": k}).mappings().all()
    return [{**r, "score": round(0.75 * r["vec"] + 0.25 * r["kw"], 4)} for r in rows]
