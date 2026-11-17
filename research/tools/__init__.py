"""Agentic AI tools suite: Modular LangChain tools for LangGraph agents.

Usage:  from tools import ALL_TOOLS   ->  llm.bind_tools(ALL_TOOLS)
        from tools import RESEARCH_WEB_TOOLS
"""
from .registry import (
    ALL_TOOLS, ALL_100_TOOLS, ALL_135_TOOLS, TOOLS_BY_NUMBER, TOOLS_BY_NAME, TOOLS_BY_CATEGORY,
    MISSING_CATEGORIES, get_tool_by_number, get_tool_by_name, list_all_tools,
)

def _safe_import(mod_name: str, attr_name: str, default=None):
    try:
        import importlib
        mod = importlib.import_module(f".{mod_name}", __package__)
        return getattr(mod, attr_name, default if default is not None else [])
    except Exception:
        return default if default is not None else []

RESEARCH_WEB_TOOLS = _safe_import("research_web", "RESEARCH_WEB_TOOLS")
ALL_RESEARCH_TOOLS = _safe_import("research_web", "ALL_RESEARCH_TOOLS")
DOC_GENERATION_TOOLS = _safe_import("doc_generation", "DOC_GENERATION_TOOLS")
FILE_OPS_TOOLS = _safe_import("file_ops", "FILE_OPS_TOOLS")



__all__ = [
     "TOOLS_BY_CATEGORY",
    "MISSING_CATEGORIES", "get_tool_by_number", "get_tool_by_name", "list_all_tools",
    "ORCHESTRATION_TOOLS", "RESEARCH_WEB_TOOLS", "ALL_RESEARCH_TOOLS", 
    "DOC_GENERATION_TOOLS", "FILE_OPS_TOOLS",
]
