from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StoredApiKeyConfig:
    id: int
    user_id: int
    alias: str
    api_key: str
    provider_type: str
    model: str
    created_at: datetime
    updated_at: datetime
