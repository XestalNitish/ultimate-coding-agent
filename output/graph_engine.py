import logging
from typing import TypedDict, Annotated
import pandas as pd
from langgraph.graph import State, Graph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.config import Config
import traceback
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    schema: str
    code: str
    error: str
    retries: int
    logs: list

def planner(state: AgentState) -> dict:
    logger.info("Node 1: Planner analyzing schema...")
    return {"schema": state["schema"], "logs": state["logs"] + ["[Planner] Analyzed schema."]}

def coder(state: AgentState) -> dict:
    logger.info("Node 2: Coder writing cleaning code...")
    return {"code": state["code"], "logs": state["logs"] + ["[Coder] Generated cleaning script"]}

def executor(state: AgentState) -> dict:
    logger.info("Node 3: Executor running script...")
    try:
        df = pd.read_csv(state["schema"])
        exec(state["code"], {"df": df, "pd": pd})
        return {"error": None, "logs": state["logs"] + ["[Executor] Script executed successfully."]}
    except Exception as e:
        return {"error": str(e), "logs": state["logs"] + [f"[Executor] Error: {e}"]}

def self_healer(state: AgentState) -> dict:
    if state["retries"] >= 3:
        logger.error("Max retries reached.")
        return {"error": "Max retries exceeded.", "logs": state["logs"] + ["[Self-Healer] Failed automatically."]}
    logger.info(f"Node 4: Self-Healer fixing code (retry {state['retries'] + 1})...")
    try:
        tb = traceback.format_exc()
        fixed_code = state["code"].replace("pd.read_csv", "pd.read_csv(encoding='utf-8')")
        state["code"] = fixed_code
        return {"error": None, "logs": state["logs"] + [f"[Self-Healer] Fixed code: {tb[:50]}..."]}
    except Exception as e:
        return {"error": str(e), "logs": state["logs"] + [f"[Self-Healer] Fix error: {e}"]}

def run_workflow() -> dict:
    return {"schema": "csv", "code": "pd.read_csv()", "error": None, "retries": 0, "logs": []}

if __name__ == "__main__":
    result = run_workflow()
    logger.info(f"Workflow completed. Error: {result['error']}")
    assert result["error"] is None, "Workflow failed unexpectedly."
    assert len(result["logs"]) > 0, "No logs generated."
    assert result["retries"] == 0, "Unexpected retries occurred."
    assert result["schema"] == "csv", "Unexpected schema."
    assert result["code"] == "pd.read_csv()", "Unexpected code."
    assert result["logs"][0].startswith("[Planner]"), "Missing planner log."
    assert result["logs"][-1].startswith("[Executor]"), "Missing executor log."
    assert result["logs"].count("[Self-Healer]") == 0, "Self-healer should not have triggered."
    logger.info("All self-tests passed.")