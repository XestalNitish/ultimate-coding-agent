# Python Core Reference for AI & Agentic Engineers

## Modern Python Type Annotations
Python 3.10+ uses native union syntax `|` instead of `Union`, and standard collections `list`, `dict`, `set`, `tuple` directly for typing without importing from `typing`.

```python
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path

def process_stream(data: list[dict[str, Any]], timeout: float | None = None) -> list[str]:
    results: list[str] = []
    for item in data:
        if val := item.get("key"):
            results.append(str(val).strip())
    return results
```

## Dataclasses and Immutability
Use dataclasses for clean domain models with type safety.

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True, slots=True)
class AgentMessage:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
```

## Asyncio Concurrency & Tasks
Run asynchronous network calls, rate limits, and parallel tool invocations.

```python
import asyncio

async def fetch_item(item_id: str) -> dict:
    await asyncio.sleep(0.1)
    return {"id": item_id, "status": "ok"}

async def gather_all(item_ids: list[str]) -> list[dict]:
    tasks = [fetch_item(i) for i in item_ids]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

## Subprocess Execution and Safety
Execute CLI tools, formatters, and sandboxed python execution.

```python
import subprocess
import sys

def execute_safe_python(code: str, timeout: int = 30) -> tuple[bool, str]:
    cmd = [sys.executable, "-c", code]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"Execution timed out after {timeout} seconds"
```

## Error Handling and Custom Exceptions
Clean exception hierarchies for production resilience.

```python
class AgentError(Exception):
    """Base error for all agent failures."""
    pass

class ToolExecutionError(AgentError):
    def __init__(self, tool_name: str, reason: str):
        super().__init__(f"Tool '{tool_name}' failed: {reason}")
        self.tool_name = tool_name
```
