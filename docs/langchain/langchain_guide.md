# LangChain Core Reference for Agentic Engineers

## Chat Models & Message Architecture
LangChain uses standard message types: `SystemMessage`, `HumanMessage`, `AIMessage`, and `ToolMessage`.

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://127.0.0.1:8082/v1",
    api_key="local-token",
    model_name="Spark-X2.5-4B",
    temperature=0.2,
    timeout=60,
    max_retries=1
)

messages = [
    SystemMessage(content="You are an expert Python engineer."),
    HumanMessage(content="Write a robust Fibonacci generator.")
]
response = llm.invoke(messages)
print(response.content)
```

## Tool Creation & Binding
Declare callable tools using `@tool` decorator with full type hints and docstrings.

```python
from langchain_core.tools import tool

@tool
def calculate_tax(amount: float, rate: float = 0.18) -> float:
    """Calculates tax on a given monetary amount with standard rate.
    
    Args:
        amount: Base amount in rupees or dollars.
        rate: Tax percentage in decimal form (default 0.18).
    """
    return round(amount * rate, 2)

# Bind tools to the LLM
llm_with_tools = llm.bind_tools([calculate_tax])
```

## Structured Output Parsing
Use Pydantic models with `with_structured_output` or JSON schemas for reliable agent outputs.

```python
from pydantic import BaseModel, Field

class FunctionPlan(BaseModel):
    function_name: str = Field(description="Name of the function in snake_case")
    arguments: list[str] = Field(description="List of parameter names with types")
    return_type: str = Field(description="Expected return type")
    docstring: str = Field(description="Docstring explanation")

structured_llm = llm.with_structured_output(FunctionPlan)
```
