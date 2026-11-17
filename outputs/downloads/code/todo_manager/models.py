from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = ""
    status: str = Field(default="pending")
    priority: str = Field(default="Medium")
    tag: str = Field(default="General")
    due_date: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())