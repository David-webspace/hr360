"""python -m app.kb.ingest：把 kb/*.md 切成「條」為單位的段落、計算 embedding、整批取代資料庫內容。"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import delete, insert

from app.db import engine
from app.kb.embedding import embed_documents
from app.models import PolicyChunk, PolicyDocument

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


@dataclass
class Doc:
    slug: str
    title: str
    version: str
    effective_from: date
    chunks: list[tuple[str, str]]  # (section_path, text)


def parse(path: Path) -> Doc:
    raw = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    body = m.group(2)
    chunks: list[tuple[str, str]] = []
    chapter, article, buf = "", "", []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            path_ = " > ".join(p for p in (meta["title"], chapter, article) if p)
            chunks.append((path_, f"【{path_}】\n{text}"))
        buf.clear()

    for line in body.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            flush()
            chapter, article = line[3:].strip(), ""
        elif line.startswith("### "):
            flush()
            article = line[4:].strip()
        else:
            buf.append(line)
    flush()
    return Doc(path.stem, meta["title"], meta["version"], date.fromisoformat(meta["effective_from"]), chunks)


def source_type(slug: str) -> str:
    return "faq" if slug.endswith("faq") else "handbook"


def main() -> None:
    docs = [parse(p) for p in sorted(KB_DIR.glob("*.md"))]
    texts = [t for d in docs for _, t in d.chunks]
    vectors = iter(embed_documents(texts))
    with engine.begin() as conn:
        conn.execute(delete(PolicyDocument))
        for d in docs:
            doc_id = conn.execute(
                insert(PolicyDocument).returning(PolicyDocument.id),
                {"slug": d.slug, "title": d.title, "version": d.version, "effective_from": d.effective_from,
                 "source_type": source_type(d.slug)},
            ).scalar_one()
            conn.execute(insert(PolicyChunk), [
                {"doc_id": doc_id, "section_path": p, "text": t, "embedding": next(vectors)} for p, t in d.chunks
            ])
    print(f"ingested {len(docs)} documents, {len(texts)} chunks")


if __name__ == "__main__":
    main()
