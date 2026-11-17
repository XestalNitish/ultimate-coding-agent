# LangGraph Agentic Orchestration Guide

## Core Concepts & Graph Initialization
LangGraph constructs stateful, multi-agent computational graphs. Every graph defines a `TypedDict` state schema, nodes (callable functions), and directed or conditional edges.

```python
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END

class AgentState(TypedDict, total=False):
    user_query: str
    research_notes: Optional[str]
    doc_context: Optional[str]
    code_output: Optional[str]
    errors: List[str]
    iteration: int
    is_complete: bool

# Initialize graph with state schema
workflow = StateGraph(AgentState)
```

## Defining Nodes
A node takes the current state dict and returns an update dict that modifies specific state keys.

```python
def researcher_node(state: AgentState) -> dict:
    query = state["user_query"]
    # Perform research or web retrieval
    notes = f"Research findings for query: {query}"
    return {"research_notes": notes}

def coder_node(state: AgentState) -> dict:
    notes = state.get("research_notes", "")
    code = f"# Generated Code\nprint('Processed with notes: {notes}')"
    return {"code_output": code, "iteration": state.get("iteration", 0) + 1}
```

## Conditional Edges and Routers
Conditional edges direct execution based on intermediate state outcomes (e.g., retry loops, test passes, fallback logic).

```python
def should_continue_router(state: AgentState) -> str:
    if state.get("is_complete"):
        return END
    if state.get("iteration", 0) >= 3:
        return "fallback_node"
    return "coder_node"

workflow.add_node("researcher", researcher_node)
workflow.add_node("coder", coder_node)

workflow.add_edge(START, "researcher")
workflow.add_edge("researcher", "coder")
workflow.add_conditional_edges(
    "coder",
    should_continue_router,
    {"coder_node": "coder", "fallback_node": END, END: END}
)

app = workflow.compile()
```

## Running & Streaming Graph Execution
Execute synchronously with `.invoke()` or stream step-by-step with `.stream()`.

```python
initial_input = {
    "user_query": "Build a fastapi app with authentication",
    "iteration": 0,
    "is_complete": False,
    "errors": []
}

# Run graph with recursion limit guard
result = app.invoke(initial_input, config={"recursion_limit": 50})
print("Final Code:", result.get("code_output"))

# Stream node executions live
for step in app.stream(initial_input):
    for node_name, state_update in step.items():
        print(f"Executed node: {node_name}")
```
