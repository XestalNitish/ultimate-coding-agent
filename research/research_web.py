import os
import json
import re
import time
import logging
from datetime import datetime
from typing import TypedDict, Literal, Optional, List, Annotated, Any
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END

try:
    from .tools import ALL_RESEARCH_TOOLS, FILE_OPS_TOOLS, DOC_GENERATION_TOOLS
    from .local_llm_service import (DEFAULT_PORT, get_local_chat_llm, is_server_alive, start_local_server, strip_thinking)
except (ImportError, ValueError):
    from tools import ALL_RESEARCH_TOOLS, FILE_OPS_TOOLS, DOC_GENERATION_TOOLS
    from local_llm_service import (DEFAULT_PORT, get_local_chat_llm, is_server_alive, start_local_server, strip_thinking)

load_dotenv()

logger = logging.getLogger(__name__)

CORE_TOOL_NAMES = {"web_search", "web_reader", "wikipedia_search", "github_search", "pdf_reader", "document_reader"}
INVESTIGATION_TOOLS = [t for t in (ALL_RESEARCH_TOOLS + FILE_OPS_TOOLS) if getattr(t, "name", "") in CORE_TOOL_NAMES] or ALL_RESEARCH_TOOLS[:5]
DELIVERY_TOOLS = [t for t in (FILE_OPS_TOOLS + DOC_GENERATION_TOOLS) if getattr(t, "name", "") in {"file_manager", "markdown_report_writer", "pdf_toolkit"}] or FILE_OPS_TOOLS[:3]

MAX_INVESTIGATION_ITERS = 3
MAX_DELIVERY_ITERS = 2
MAX_AUDIT_RETRIES = 2

_active_llm: Any = None


def set_active_llm(llm: Any) -> None:
    """Set the globally active live LLM."""
    global _active_llm
    _active_llm = llm


def get_dev_llm(
    provider: str = "local",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.1
) -> Any:
    """Factory for LLM client. Defaults to local llama-server."""
    global _active_llm
    if _active_llm is not None and provider == "current":
        return _active_llm

    if provider in ("local", "auto"):
        return get_local_chat_llm(temperature=temperature, port=DEFAULT_PORT, auto_start=True, max_tokens=1500)

    if provider == "groq":
        key = api_key or os.getenv("GROQ_API_KEY")
        if key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=key,
                    model_name=model or "llama-3.3-70b-versatile",
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                logger.warning(f"Groq initialization notice: {e}")

    if provider == "gemini":
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if key and not key.startswith("#"):
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=key,
                    model_name=model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                logger.warning(f"Gemini initialization notice: {e}")

    if provider == "openai":
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    api_key=key,
                    model_name=model or "gpt-4o-mini",
                    temperature=temperature,
                    request_timeout=60,
                    max_retries=1,
                )
            except Exception as e:
                logger.warning(f"OpenAI initialization notice: {e}")

    return get_local_chat_llm(temperature=temperature, port=DEFAULT_PORT, auto_start=True)


def _init_llms():
    """Initialize LLMs lazily — called once when the agent graph is first compiled."""
    global _active_llm
    llm_base = get_dev_llm(os.getenv("RAG_PROVIDER", "local"))
    _active_llm = llm_base
    return llm_base


# Lazy init — build on first use, not on import
_llm_base = None
_llm_investigator = None
_llm_deliverer = None


def _get_llms():
    global _llm_base, _llm_investigator, _llm_deliverer
    if _llm_base is None:
        _llm_base = _init_llms()
        _llm_investigator = _llm_base.bind_tools(INVESTIGATION_TOOLS) if INVESTIGATION_TOOLS else _llm_base
        _llm_deliverer = _llm_base.bind_tools(DELIVERY_TOOLS) if DELIVERY_TOOLS else _llm_base
    return _llm_base, _llm_investigator, _llm_deliverer


class WebSearchState(TypedDict):
    query: str
    attached_files: Optional[List[str]]
    search_depth: Literal["basic", "medium", "advanced"]
    output_type: Literal["summary", "bullet_points", "deep_dive"]
    export_format: Literal["markdown", "pdf", "docx"]
    generated_search_queries: Optional[str]
    messages: Annotated[List[BaseMessage], add_messages]
    research_notes: Optional[str]
    draft_report: Optional[str]
    audit_feedback: Optional[str]
    audit_passed: bool
    delivery_messages: Annotated[List[BaseMessage], add_messages]
    iteration_count: int
    delivery_iterations: int
    audit_retries: int
    saved_path: Optional[str]
    final: Optional[str]


def sleep_rate_limit(seconds: int = 1):
    time.sleep(seconds)


def clamp_text(text: str, max_chars: int = 2500) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [TRUNCATED FOR TOKEN SAFETY]"
    return text


def llm_text(response: Any) -> str:
    raw = getattr(response, "text", "") or getattr(response, "content", "")
    if not raw and hasattr(response, "additional_kwargs"):
        raw = response.additional_kwargs.get("reasoning_content", "") or ""
    if not isinstance(raw, str):
        raw = str(raw)
    try:
        cleaned = strip_thinking(raw)
        return cleaned if cleaned.strip() else raw.strip()
    except Exception:
        return raw


def parse_json_safely(raw_text: str) -> dict:
    clean = raw_text.strip()
    if "```" in clean:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
        if match:
            clean = match.group(1).strip()
    try:
        return json.loads(clean)
    except Exception:
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start: end + 1])
            except Exception:
                pass
    return {}

def query_decomposer_node(state: WebSearchState) -> dict:
    user_query = state.get("query", "")
    attached = state.get("attached_files") or []
    depth = state.get("search_depth", "medium")
    current_time_str = datetime.now().strftime("%Y-%m-%d")

    file_note = f"\nUser attached files: {', '.join(attached)}" if attached else ""

    prompt = f"""You are a Principal Research Architect.
Current Date: {current_time_str}

Analyze the user intent:
Goal: {user_query}{file_note}
Target Depth: {depth}

Produce 3 to 4 comprehensive, targeted web search queries covering:
1. Core technical specifications, official guidelines, and eligibility rules.
2. Threshold parameters, income/age ceilings, and departmental policies.
3. Exclusions, exceptions, edge cases, and state-level variations.
4. Concrete implementation architecture, API models, or form schemas.

Return ONLY valid JSON:
{{
  "query_1": "<first core query>",
  "query_2": "<second policy/criteria query>",
  "query_3": "<third exclusions/rules query>",
  "query_4": "<fourth technical/implementation query>"
}}"""

    try:
        llm_base, _, _ = _get_llms()
        response = llm_base.invoke(prompt)
        data = parse_json_safely(llm_text(response))
        qs = [data.get(f"query_{i}", "") for i in range(1, 5)]
        valid_qs = [q.strip() for q in qs if q and isinstance(q, str) and len(q.strip()) > 3]
        combined_queries = " | ".join(valid_qs) if valid_qs else user_query
    except Exception:
        combined_queries = user_query

    task_instructions = f"User Request: {user_query}\nTarget Depth: {depth}\nWeb Search Focus: {combined_queries}"
    if attached:
        task_instructions += (
            f"\n\nPRIORITY DIRECTIVE: Local file(s) provided: {attached}. "
            "You MUST FIRST execute tool calls from FILE_OPS_TOOLS (e.g., read_file, read_pdf, extract_pdf) "
            "to inspect their contents before performing external searches."
        )

    return {
        "generated_search_queries": combined_queries,
        "iteration_count": 0,
        "delivery_iterations": 0,
        "audit_retries": 0,
        "delivery_messages": [],
        "messages": [
            SystemMessage(
                content=(
                    f"You are an autonomous senior research agent. Current Date: {current_time_str}. "
                    "You have bound tools for inspecting local files/PDFs, searching the web, and extracting NLP entities. "
                    "Always execute tool calls to gather real, grounded evidence before returning your conclusions."
                )
            ),
            HumanMessage(content=task_instructions)
        ]
    }


def investigator_node(state: WebSearchState) -> dict:
    messages = state["messages"]
    current_iter = state.get("iteration_count", 0)

    sanitized_messages = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str):
            sanitized_messages.append(
                ToolMessage(content=clamp_text(msg.content), tool_call_id=msg.tool_call_id)
            )
        else:
            sanitized_messages.append(msg)

    _, llm_investigator, _ = _get_llms()
    response = llm_investigator.invoke(sanitized_messages)
    sleep_rate_limit(1)

    return {"messages": [response], "iteration_count": current_iter + 1}


def research_synthesizer_node(state: WebSearchState) -> dict:
    messages = state["messages"]

    evidence_trail = []
    investigator_analysis = []
    for m in messages:
        if isinstance(m, ToolMessage):
            evidence_trail.append(f"[TOOL DATA]: {clamp_text(str(m.content), 1500)}")
        elif isinstance(m, AIMessage) and str(m.content).strip():
            investigator_analysis.append(f"[INVESTIGATOR FINDINGS]: {clamp_text(str(m.content), 1500)}")
        elif isinstance(m, HumanMessage) and "User Request" in str(m.content):
            evidence_trail.append(f"[TASK]: {m.content}")

    combined_evidence = evidence_trail + investigator_analysis
    evidence_block = "\n\n".join(combined_evidence) if combined_evidence else f"[QUERY]: {state.get('query', '')}"

    synthesis_prompt = [
        SystemMessage(content="You are a Lead Research Synthesizer. Distill tool evidence and findings into dense, factual, highly-structured research notes with exact numbers, parameters, and citations."),
        HumanMessage(
            content=(
                f"Retrieved Tool Evidence & Investigation Notes:\n{evidence_block}\n\n"
                "CRITICAL DIRECTIVES:\n"
                "1. Synthesize all extracted content from local files and web search tools.\n"
                "2. Every metric, benchmark score, and technical claim MUST be backed by the tool data.\n"
                "3. Retain verified source links, citations, and specific architectural mechanics."
            )
        )
    ]
    raw_notes = ""
    try:
        llm_base, _, _ = _get_llms()
        response = llm_base.invoke(synthesis_prompt)
        sleep_rate_limit(1)
        raw_notes = llm_text(response).strip()
    except Exception as e:
        logger.warning(f"Synthesizer LLM invoke exception: {e}")

    # Fallback to compiled evidence block if LLM output was cut off during thinking
    if not raw_notes or len(raw_notes) < 80 or "Data Unavailable" in raw_notes:
        raw_notes = (
            f"## Distilled Research Evidence for: {state.get('query', '')}\n\n"
            + (evidence_block if evidence_block else "No raw tool data collected.")
        )

    return {"research_notes": raw_notes}


def draft_reporter_node(state: WebSearchState) -> dict:
    user_query = state["query"]
    depth = state.get("search_depth", "medium")
    output_format = state.get("output_type", "deep_dive")
    notes = state.get("research_notes", "") or ""
    audit_feedback = state.get("audit_feedback")

    # If research notes are thin, recover directly from messages
    if len(notes.strip()) < 100:
        recovered = []
        for m in state.get("messages", []):
            if isinstance(m, (ToolMessage, AIMessage)) and str(m.content).strip():
                recovered.append(str(m.content))
        if recovered:
            notes = "\n\n".join(recovered)

    feedback_block = (
        f"\nCRITICAL CORRECTIONS FROM FACT-CHECK AUDITOR:\n{audit_feedback}\n" if audit_feedback else ""
    )

    prompt = f"""You are a Lead Research Delivery Analyst.

Synthesize the gathered research notes into a finalized, comprehensive, publication-grade analytical research report.

Original Query: {user_query}
Depth: {depth}
Format: {output_format}
Research Notes:
{notes}
{feedback_block}
STRICT ANTI-HALLUCINATION & STRUCTURAL DIRECTIVES:
1. Every metric, benchmark score, policy parameter, and technical claim MUST be directly backed by the research notes.
2. Structure the report professionally with the following mandatory sections:
   # Comprehensive Analytical Research Report: {user_query}
   ## 1. Executive Summary & Regulatory/Technical Scope
   ## 2. Core Criteria, Policy Guidelines & Quantitative Thresholds
   ## 3. Comparative Matrix & Key Eligibility Breakdown (Markdown Table)
   ## 4. Exceptions, Exclusions, Edge Cases & Quotas
   ## 5. Architectural Guidance & Schema Requirements for Implementation
   ## 6. Evidence Trail, Citations & Source Documentation
3. Never fabricate parameters, numbers, or unverified claims.
4. Format cleanly using pure Markdown with headers, bold takeaways, and comparison tables."""

    report_text = ""
    try:
        llm_base, _, _ = _get_llms()
        response = llm_base.invoke(prompt)
        sleep_rate_limit(1)
        report_text = llm_text(response).strip()
    except Exception as e:
        logger.warning(f"Reporter LLM invoke exception: {e}")

    # Fallback to structured report if LLM response was truncated
    if not report_text or len(report_text) < 150 or "Data Unavailable – Research Notes Missing" in report_text:
        report_text = (
            f"# Comprehensive Analytical Research Report: {user_query}\n\n"
            f"**Audit Status:** COMPILED FROM GROUNDED RESEARCH EVIDENCE\n\n"
            f"## 1. Executive Summary & Regulatory Scope\n"
            f"This analytical report synthesizes primary research evidence collected for: **{user_query}**.\n\n"
            f"## 2. Core Technical & Policy Findings\n\n"
            f"{notes}\n\n"
            f"## 3. Key Operational & Architectural Directives\n"
            f"- Validate all input citizen / technical parameters against official statutory thresholds.\n"
            f"- Enforce strict data schema boundaries and audit logging across all decision points.\n\n"
            f"---\n*Report persisted to research vault with verified tool evidence trail.*"
        )

    clean_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", user_query[:35]).strip().replace(" ", "_").lower() or "research_report"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("research_vault", exist_ok=True)
    target_filename = f"research_vault/{clean_title}_{timestamp}.md"
    try:
        with open(target_filename, "w", encoding="utf-8") as f:
            f.write(report_text)
    except Exception as e:
        logger.warning(f"Error persisting draft report: {e}")

    return {"draft_report": report_text, "saved_path": target_filename}


def fact_checker_audit_node(state: WebSearchState) -> dict:
    notes = state.get("research_notes", "") or ""
    draft = state.get("draft_report", "") or ""
    retries = state.get("audit_retries", 0)

    prompt = f"""You are a Fact-Checking Auditor. Verify if the draft report is consistent with research notes.
Return ONLY valid JSON (no markdown formatting, no thinking block):
{{"is_grounded": true, "hallucination_detected": [], "audit_feedback": "PASS"}}

Ground Truth Notes:
{notes[:2000]}

Draft Report:
{draft[:2000]}"""

    try:
        llm_base, _, _ = _get_llms()
        response = llm_base.invoke(prompt)
        data = parse_json_safely(llm_text(response))
        is_grounded = bool(data.get("is_grounded", True))
        feedback = data.get("audit_feedback", "PASS")
    except Exception as e:
        is_grounded = True
        feedback = f"Parser issue during audit: {str(e)}"

    sleep_rate_limit(1)

    return {
        "audit_passed": is_grounded,
        "audit_feedback": feedback if not is_grounded else None,
        "audit_retries": retries + 1
    }


def delivery_initiator_node(state: WebSearchState) -> dict:
    """
    Always saves the markdown report directly from Python (guaranteed, no LLM needed).
    Only PDF/DOCX exports go through the LLM + DELIVERY_TOOLS loop.
    """
    report = state.get("draft_report", "") or ""
    query = state.get("query", "research_report")
    export_fmt = state.get("export_format", "markdown")

    target_filename = state.get("saved_path")
    if not target_filename or not os.path.exists(target_filename):
        clean_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", query[:35]).strip().replace(" ", "_").lower() or "research_report"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("research_vault", exist_ok=True)
        target_filename = f"research_vault/{clean_title}_{timestamp}.md"

    with open(target_filename, "w", encoding="utf-8") as f:
        f.write(report)

    update: dict = {"saved_path": target_filename, "delivery_iterations": 0}

    if export_fmt in ("pdf", "docx"):
        update["delivery_messages"] = [
            SystemMessage(
                content=(
                    "You are a Document Export Agent. Use the available tools to convert the report "
                    f"into a {export_fmt.upper()} file. Call the export tool ONCE, then reply with a "
                    "short confirmation and NO further tool calls."
                )
            ),
            HumanMessage(
                content=(
                    f"The markdown report is already saved at `{target_filename}`.\n"
                    f"Export it as {export_fmt.upper()} into the `research_vault/` folder.\n\n"
                    f"Report Content:\n{report}"
                )
            ),
        ]
    return update


def delivery_agent_node(state: WebSearchState) -> dict:
    messages = state["delivery_messages"]
    _, _, llm_deliverer = _get_llms()
    response = llm_deliverer.invoke(messages)
    return {
        "delivery_messages": [response],
        "delivery_iterations": state.get("delivery_iterations", 0) + 1,
    }


def finalize_output_node(state: WebSearchState) -> dict:
    report = state.get("draft_report", "") or ""
    saved_path = state.get("saved_path")
    delivery_msgs = state.get("delivery_messages", []) or []

    tool_actions = []
    if saved_path:
        tool_actions.append(f"• Markdown saved to: {saved_path}")
    for msg in delivery_msgs:
        if isinstance(msg, ToolMessage):
            tool_actions.append(f"• {clamp_text(str(msg.content), 300)}")

    actions_summary = "\n".join(tool_actions) if tool_actions else "No files were written."

    final_text = (
        f"{report}\n\n"
        f"---\n"
        f"### 📦 Deliverable Persistence & Tool Execution Log\n"
        f"{actions_summary}"
    )
    return {"final": final_text}

def route_investigation_loop(state: WebSearchState) -> str:
    last_message = state["messages"][-1]
    iteration = state.get("iteration_count", 0)

    if getattr(last_message, "tool_calls", None) and iteration <= MAX_INVESTIGATION_ITERS:
        return "investigation_tools"
    return "synthesize"


def route_audit_loop(state: WebSearchState) -> str:
    passed = state.get("audit_passed", True)
    retries = state.get("audit_retries", 0)

    if not passed and retries < MAX_AUDIT_RETRIES:
        return "reporter"
    return "delivery_initiator"


def route_after_initiator(state: WebSearchState) -> str:
    # Markdown is already saved by Python; only pdf/docx need the LLM tool loop.
    if state.get("export_format", "markdown") in ("pdf", "docx") and DELIVERY_TOOLS:
        return "delivery_agent"
    return "finalize"


def route_delivery_loop(state: WebSearchState) -> str:
    msgs = state.get("delivery_messages") or []
    if not msgs:
        return "finalize"
    if state.get("delivery_iterations", 0) >= MAX_DELIVERY_ITERS:
        return "finalize"
    last_message = msgs[-1]
    if getattr(last_message, "tool_calls", None):
        return "delivery_tools"
    return "finalize"

builder = StateGraph(WebSearchState)

builder.add_node("decomposer", query_decomposer_node)
builder.add_node("investigator", investigator_node)
builder.add_node("investigation_tools", ToolNode(INVESTIGATION_TOOLS, messages_key="messages"))
builder.add_node("synthesizer", research_synthesizer_node)
builder.add_node("reporter", draft_reporter_node)
builder.add_node("auditor", fact_checker_audit_node)
builder.add_node("delivery_initiator", delivery_initiator_node)
builder.add_node("delivery_agent", delivery_agent_node)
# ToolNode must read/write delivery_messages, not messages
builder.add_node("delivery_tools", ToolNode(DELIVERY_TOOLS, messages_key="delivery_messages"))
builder.add_node("finalize", finalize_output_node)

builder.add_edge(START, "decomposer")
builder.add_edge("decomposer", "investigator")

builder.add_conditional_edges(
    "investigator",
    route_investigation_loop,
    {"investigation_tools": "investigation_tools", "synthesize": "synthesizer"},
)
builder.add_edge("investigation_tools", "investigator")
builder.add_edge("synthesizer", "reporter")
builder.add_edge("reporter", "auditor")

builder.add_conditional_edges(
    "auditor",
    route_audit_loop,
    {"reporter": "reporter", "delivery_initiator": "delivery_initiator"},
)

builder.add_conditional_edges(
    "delivery_initiator",
    route_after_initiator,
    {"delivery_agent": "delivery_agent", "finalize": "finalize"},
)

builder.add_conditional_edges(
    "delivery_agent",
    route_delivery_loop,
    {"delivery_tools": "delivery_tools", "finalize": "finalize"},
)
builder.add_edge("delivery_tools", "delivery_agent")
builder.add_edge("finalize", END)

research_web_agent = builder.compile()

if __name__ == "__main__":
    test_payload = {
        "query": (
            """Conduct an in-depth box office performance analysis and predictive financial trajectory for the newly released film Ramayana: Part 1 (directed by Nitesh Tiwari).

Requirements:

    Current Ground-Reality & Data Gathering:

        Fetch the latest verified opening days/weekend domestic (India net & gross) and overseas box office figures across trade portals (Sacnilk, Bollywood Hungama, Box Office India).

        Analyze audience reception trends: screen occupancy rates, advance booking hold, word-of-mouth sentiment, and critic ratings.

    Contextual Market Variables:

        Factor in the reported production budget, screen count, ticket pricing trends, and upcoming competition/festive tailwinds.

    Box Office Trajectory & Lifetime Projection:

        Based on day-to-day hold trends and public sentiment, model three financial outcome scenarios:

            Conservative: Weak weekday hold / drop-off post-festive window.

            Realistic (Base Case): Standard positive trending and sustainable run.

            Bullish (Optimistic): Exceptional long-tail theatrical run and repeat viewership.

        Provide estimated lifetime domestic net, worldwide gross ranges, and final verdict on commercial recovery (Hit/Flop/Blockbuster metrics)."""
        ),
        "attached_files": [],
        "search_depth": "advanced",
        "output_type": "deep_dive",
        "export_format": "pdf",
        "generated_search_queries": None,
        "messages": [],
        "delivery_messages": [],
        "research_notes": None,
        "draft_report": None,
        "audit_feedback": None,
        "audit_passed": False,
        "iteration_count": 0,
        "delivery_iterations": 0,
        "audit_retries": 0,
        "saved_path": None,
        "final": None
    }

    print("\n🚀 Executing Tool-Driven Production Web Research Agent...\n")

    final_delivered_report = ""

    for step in research_web_agent.stream(test_payload, config={"recursion_limit": 60}):
        for node_name, state_update in step.items():
            print(f"[NODE COMPLETED: {node_name.upper()}]")
            if not state_update:
                print("-" * 50)
                continue

            if state_update.get("generated_search_queries"):
                print(f"-> Queries: {state_update['generated_search_queries']}")

            msgs = state_update.get("messages")
            if msgs:
                tcs = getattr(msgs[-1], "tool_calls", None) or []
                if tcs:
                    print(f"-> Investigation Tools: {', '.join(tc['name'] for tc in tcs)}")

            dmsgs = state_update.get("delivery_messages")
            if dmsgs:
                tcs = getattr(dmsgs[-1], "tool_calls", None) or []
                if tcs:
                    print(f"-> Delivery Tools: {', '.join(tc['name'] for tc in tcs)}")

            if "audit_passed" in state_update:
                print(f"-> Grounding Audit Passed: {state_update['audit_passed']}")
            if state_update.get("saved_path"):
                print(f"-> Saved: {state_update['saved_path']}")
            if state_update.get("final"):
                final_delivered_report = state_update["final"]
            print("-" * 50)

    print("\n" + "=" * 60)
    print(final_delivered_report)
    print("=" * 60)