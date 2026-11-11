from functools import lru_cache

from fastembed import TextEmbedding

from app.config import settings

# bge 中文模型官方建議：查詢句加上指令前綴，文件段落不加
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(settings.embedding_model, cache_dir=settings.model_cache_dir)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts, batch_size=32)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().embed([QUERY_PREFIX + text]))).tolist()
