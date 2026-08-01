from contextvars import ContextVar


generation_id: ContextVar[str | None] = ContextVar("generation_id", default=None)


def log_context() -> dict[str, str]:
    value = generation_id.get()
    return {"generation_id": value} if value is not None else {}
