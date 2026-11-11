from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.agent.llm import Usage
from app.auth import Principal
from app.config import settings
from app.models import AuditLog


@lru_cache(maxsize=1)
def _pricing() -> dict:
    return yaml.safe_load(Path(settings.llm_pricing_file).read_text())


def cost_usd(model_usage: dict[str, Usage]) -> float | None:
    total = 0.0
    for model, u in model_usage.items():
        price = _pricing().get(model)
        if price is None:
            return None
        total += (u.input * price["input"] + u.output * price["output"] + u.cache_read * price["cache_read"]
                  + u.cache_write * price["cache_write"]) / 1_000_000
    return round(total, 6)


def write(db: Session, p: Principal | None, event: str, *, channel: str = "web", question: str | None = None,
          intent: str | None = None, model: str | None = None, routed_by: str | None = None, tools: list | None = None,
          denied: bool = False, deny_reason: str | None = None, usage: Usage | None = None, cost: float | None = None,
          latency_ms: int | None = None, grounding_ok: bool | None = None, conversation_id: int | None = None) -> None:
    u = usage or Usage()
    db.execute(insert(AuditLog), {
        "user_id": p.user_id if p else None, "roles": sorted(p.roles) if p else [], "channel": channel, "event": event,
        "question": question, "intent": intent, "model": model, "routed_by": routed_by, "tools": tools,
        "denied": denied, "deny_reason": deny_reason, "input_tokens": u.input, "output_tokens": u.output,
        "cache_read_tokens": u.cache_read, "cache_write_tokens": u.cache_write, "cost_usd": cost,
        "latency_ms": latency_ms, "grounding_ok": grounding_ok, "conversation_id": conversation_id,
    })
    db.commit()
