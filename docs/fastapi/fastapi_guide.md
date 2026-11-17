# FastAPI Production Guide for AI Services

## FastAPI Application & Async Endpoints
Build async REST APIs with automatic OpenAPI (Swagger) documentation.

```python
from fastapi import FastAPI, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field

app = FastAPI(
    title="AI Agent API",
    version="1.0.0",
    description="Production REST endpoints for multi-agent workflows."
)

class QueryRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000)
    max_tokens: int = Field(default=512, ge=16, le=4096)

class QueryResponse(BaseModel):
    response: str
    tokens_used: int
    status: str = "success"

@app.post("/v1/generate", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def generate_completion(payload: QueryRequest):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    return QueryResponse(response=f"Echo: {payload.prompt}", tokens_used=120)
```

## Background Tasks
Run heavy background jobs (e.g. document embedding, model fine-tuning) without blocking response.

```python
from fastapi import BackgroundTasks

def background_ingest(file_path: str):
    # Heavy document processing
    print(f"Background indexing completed for: {file_path}")

@app.post("/v1/ingest")
async def ingest_file(file_path: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(background_ingest, file_path)
    return {"message": "Ingestion scheduled in background"}
```

## Running the Server
Execute via Uvicorn CLI or programmatic runner:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
