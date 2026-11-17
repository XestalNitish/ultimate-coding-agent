from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List
import database
import graph_engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class WorkflowRequest(BaseModel):
    csv_file: UploadFile
    pdf_file: UploadFile

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    data: List[dict]

@app.post("/workflow")
async def generate_completion(payload: WorkflowRequest):
    logger.info("Triggering Project Leviathan workflow...")
    try:
        result = graph_engine.run_workflow()
        logger.info(f"Workflow completed. Status: {result.get('status', 'Success')}")
        return {"status": "success", "logs": result.get("logs", []), "data": result.get("data", [])}
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def query_data(payload: QueryRequest):
    logger.info(f"Executing query: {payload.query}")
    try:
        cleaned_data = await database.AsyncDB().query_data(payload.query, limit=10)
        return QueryResponse(data=[d.model_dump() for d in cleaned_data])
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)