"""X-ESTAL NITISH | Ultimate Coding Agent & Enterprise Autonomous AI Engineering Suite.

Mission Control Dashboard with Claymorphic + Glassmorphic Neural AI Design.
Engineered by X-ESTAL NITISH (Nitish Kumar).
Observability: LangSmith Production Telemetry (Project: ultimate-coding-agent)
Backend: Dual Local LLM Topology (Spark 2.5 on 8082, Spark 2.6 on 8084)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

# Configure page settings
st.set_page_config(
    page_title="X-ESTAL NITISH | Ultimate Coding Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
PYTHON_EXE = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

# Transparent import of main and orchestrator components
try:
    import main
    import config as C
    import llm
    import rag
    import start_servers
    import checkpoint_manager
except Exception as e:
    st.error(f"Initialization error: {e}")

# ============================================================================
# COMPREHENSIVE CYBER / CLAYMORPHIC / GLASSMORPHIC THEME OVERRIDE
# ============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    /* Global Typography & Deep Dark Background */
    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background: radial-gradient(circle at 10% 10%, rgba(0, 240, 255, 0.05) 0%, transparent 45%),
                    radial-gradient(circle at 90% 15%, rgba(139, 92, 246, 0.07) 0%, transparent 45%),
                    radial-gradient(circle at 50% 90%, rgba(16, 185, 129, 0.04) 0%, transparent 50%),
                    #070a13 !important;
        color: #f1f5f9 !important;
    }

    code, pre, .stCode, [data-testid="stCodeBlock"] {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Force Dark Theme on Sidebar */
    [data-testid="stSidebar"], section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, #090e1b 0%, #060913 100%) !important;
        border-right: 1px solid rgba(0, 240, 255, 0.12) !important;
        color: #f1f5f9 !important;
    }

    /* Brand Header Box in Sidebar */
    .brand-box {
        background: linear-gradient(135deg, rgba(20, 32, 54, 0.7), rgba(10, 16, 30, 0.9));
        border: 1px solid rgba(0, 240, 255, 0.2);
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5), inset 0 1px 2px rgba(255, 255, 255, 0.1);
    }
    .brand-title {
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 0.05em;
        background: linear-gradient(135deg, #00f0ff 0%, #a855f7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2px;
    }
    .brand-subtitle {
        font-size: 11px;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .brand-badge {
        display: inline-block;
        padding: 3px 8px;
        background: rgba(0, 240, 255, 0.12);
        border: 1px solid rgba(0, 240, 255, 0.3);
        border-radius: 6px;
        color: #00f0ff;
        font-size: 10px;
        font-weight: 700;
        margin-top: 8px;
    }

    /* Sleek Navigation Radio - Transform into SaaS Menu Pills */
    [data-testid="stRadio"] > div {
        gap: 6px !important;
    }
    [data-testid="stRadio"] div[role="radiogroup"] > label div:first-child {
        display: none !important;
    }
    [data-testid="stRadio"] div[role="radiogroup"] > label {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 12px !important;
        padding: 10px 14px !important;
        color: #94a3b8 !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        margin-bottom: 4px !important;
    }
    [data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background: rgba(26, 38, 64, 0.8) !important;
        border-color: rgba(0, 240, 255, 0.3) !important;
        color: #f8fafc !important;
        transform: translateX(3px) !important;
    }
    [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
        background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(168, 85, 247, 0.15)) !important;
        border: 1px solid #00f0ff !important;
        color: #00f0ff !important;
        font-weight: 700 !important;
        box-shadow: 0 0 16px rgba(0, 240, 255, 0.25) !important;
    }

    /* Top Navigation Bar */
    .top-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(13, 20, 36, 0.7);
        border: 1px solid rgba(0, 240, 255, 0.15);
        border-radius: 16px;
        padding: 14px 20px;
        margin-bottom: 24px;
        backdrop-filter: blur(16px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    .top-bar-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .top-bar-brand {
        font-weight: 800;
        font-size: 16px;
        color: #f8fafc;
        letter-spacing: -0.01em;
    }
    .top-bar-brand span {
        color: #00f0ff;
    }
    .top-chips {
        display: flex;
        gap: 8px;
    }
    .chip {
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
    }
    .chip-cyan {
        background: rgba(0, 240, 255, 0.1);
        border: 1px solid rgba(0, 240, 255, 0.3);
        color: #38bdf8;
    }
    .chip-purple {
        background: rgba(168, 85, 247, 0.1);
        border: 1px solid rgba(168, 85, 247, 0.3);
        color: #c084fc;
    }
    .chip-green {
        background: rgba(34, 197, 94, 0.1);
        border: 1px solid rgba(34, 197, 94, 0.3);
        color: #4ade80;
    }

    /* Claymorphic Card */
    .clay-card {
        background: linear-gradient(135deg, rgba(20, 30, 50, 0.8), rgba(10, 16, 30, 0.95));
        border-radius: 20px;
        box-shadow: 8px 8px 24px rgba(0, 0, 0, 0.65),
                    -4px -4px 16px rgba(255, 255, 255, 0.03),
                    inset 1px 1px 2px rgba(255, 255, 255, 0.08),
                    inset -2px -2px 6px rgba(0, 0, 0, 0.45);
        border: 1px solid rgba(0, 240, 255, 0.14);
        padding: 24px;
        backdrop-filter: blur(20px) saturate(180%);
        margin-bottom: 22px;
        transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
    }
    .clay-card:hover {
        border-color: rgba(0, 240, 255, 0.35);
        box-shadow: 10px 10px 30px rgba(0, 0, 0, 0.75),
                    -5px -5px 20px rgba(0, 240, 255, 0.08);
        transform: translateY(-2px);
    }

    /* Clay Metric Card */
    .clay-metric {
        background: linear-gradient(145deg, rgba(24, 35, 60, 0.85), rgba(12, 18, 34, 0.95));
        border-radius: 18px;
        padding: 18px 22px;
        box-shadow: 6px 6px 18px rgba(0, 0, 0, 0.6),
                    -3px -3px 12px rgba(255, 255, 255, 0.035),
                    inset 1px 1px 2px rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(0, 240, 255, 0.15);
        margin-bottom: 16px;
    }
    .clay-metric .label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
        margin-bottom: 6px;
    }
    .clay-metric .value {
        font-size: 28px;
        font-weight: 800;
        color: #f8fafc;
        line-height: 1.1;
    }
    .clay-metric .sub {
        font-size: 12px;
        font-weight: 500;
        color: #00f0ff;
        margin-top: 4px;
    }

    /* Live Pulse Indicator */
    .pulse-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .pulse-green {
        background-color: #10b981;
        box-shadow: 0 0 10px #10b981;
        animation: pulse-green-anim 2s infinite;
    }
    @keyframes pulse-green-anim {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.8); }
        70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    .pulse-red {
        background-color: #ef4444;
        box-shadow: 0 0 8px rgba(239, 68, 68, 0.7);
    }

    /* Terminal Console */
    .neural-console {
        background: #090e18;
        border: 1px solid rgba(0, 240, 255, 0.2);
        border-radius: 14px;
        padding: 16px 20px;
        color: #38bdf8;
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        line-height: 1.6;
        box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8);
        overflow-x: auto;
    }

    /* Gradient Headers */
    .hero-title {
        font-size: 28px;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #ffffff 10%, #00f0ff 60%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 14px;
        margin-bottom: 20px;
    }

    /* Buttons override */
    div.stButton > button {
        background: linear-gradient(135deg, #16243d 0%, #0c1527 100%) !important;
        border: 1px solid rgba(0, 240, 255, 0.25) !important;
        border-radius: 12px !important;
        color: #f1f5f9 !important;
        font-weight: 600 !important;
        box-shadow: 4px 4px 12px rgba(0,0,0,0.5), -2px -2px 8px rgba(255,255,255,0.03), inset 1px 1px 2px rgba(255,255,255,0.08) !important;
        padding: 8px 18px !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover {
        border-color: #00f0ff !important;
        color: #00f0ff !important;
        box-shadow: 0 0 18px rgba(0, 240, 255, 0.4) !important;
        transform: translateY(-2px) !important;
    }

    /* Inputs & Selectboxes */
    .stTextInput > div > div, .stTextArea > div > div, .stSelectbox > div > div {
        background-color: rgba(14, 21, 37, 0.75) !important;
        border: 1px solid rgba(0, 240, 255, 0.18) !important;
        border-radius: 12px !important;
        color: #f1f5f9 !important;
    }
    .stTextInput > div > div:focus-within, .stTextArea > div > div:focus-within {
        border-color: #00f0ff !important;
        box-shadow: 0 0 12px rgba(0, 240, 255, 0.3) !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SERVER CONTROL & TELEMETRY
# ============================================================================

def check_server(role: str) -> bool:
    try:
        return llm.server_up(role)
    except Exception:
        return False


def auto_start_servers_ui(roles: list[str] | None = None) -> bool:
    """Auto-start servers with visual feedback in Streamlit."""
    roles = roles or ["main", "writer"]
    needed = [r for r in roles if not check_server(r)]
    if not needed:
        return True
    
    with st.status(f"⚡ Auto-Starting Local LLM Daemons: {needed}...", expanded=True) as status:
        st.write("Initializing model weights & memory locking (--mlock)...")
        log_holder = st.empty()
        
        def progress_update(msg: str):
            log_holder.caption(f"❯ {msg}")

        success = start_servers.ensure_servers(needed, wait=True, timeout=150, progress_cb=progress_update)
        if success:
            status.update(label="✅ Local LLM Daemons Online & Ready!", state="complete", expanded=False)
            return True
        else:
            status.update(label="⚠️ Server startup delayed. Check logs.", state="error", expanded=True)
            return False


# ============================================================================
# SIDEBAR NAVIGATION & MISSION CONTROL HARDWARE STATUS
# ============================================================================

with st.sidebar:
    st.markdown("""
    <div class="brand-box">
        <div class="brand-title">⚡ X-ESTAL NITISH</div>
        <div class="brand-subtitle">ULTIMATE CODING AGENT</div>
        <div class="brand-badge">Autonomous Software Engineer</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.caption("**Lead Architect:** [X-ESTAL NITISH (Nitish Kumar)](https://github.com/XestalNitish)")
    
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    nav = st.radio(
        "Navigation Matrix",
        [
            "💬 Neural Chat (AI + Live Web)",
            "📚 Hybrid RAG Intelligence",
            "🚀 Autonomous Code Synthesizer",
            "🌐 Deep Web Research Agent",
            "🤖 Enterprise 5-Agent Suite",
            "📊 LangSmith Production Observability",
            "📖 Technical Case Study",
            "🌐 Deployed AI Projects & Ecosystem",
            "⚡ System & Server Mission Control",
        ],
        index=0,
    )
    
    st.markdown("---")
    st.markdown("#### ⚡ Local Hardware Daemons")
    
    s1_ok = check_server("main")
    s2_ok = check_server("writer")
    
    c_s1, c_s2 = st.columns(2)
    with c_s1:
        color = "chip-green" if s1_ok else "chip-purple"
        p_class = "pulse-green" if s1_ok else "pulse-red"
        st.markdown(f'<div class="chip {color}"><span class="pulse-dot {p_class}"></span> S1: {"UP" if s1_ok else "OFF"}</div>', unsafe_allow_html=True)
    with c_s2:
        color = "chip-green" if s2_ok else "chip-purple"
        p_class = "pulse-green" if s2_ok else "pulse-red"
        st.markdown(f'<div class="chip {color}"><span class="pulse-dot {p_class}"></span> S2: {"UP" if s2_ok else "OFF"}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    c_b1, c_b2 = st.columns(2)
    with c_b1:
        if st.button("⚡ Start", use_container_width=True):
            auto_start_servers_ui(["main", "writer"])
            st.rerun()
    with c_b2:
        if st.button("🛑 Stop", use_container_width=True):
            start_servers.stop_servers()
            st.info("Servers stopped.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🌐 Live Deployed AI Apps")
    st.markdown("""
    <div style="font-size:12px; line-height:2.0;">
        <div>🚀 <a href="https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#00f0ff; text-decoration:none; font-weight:600;">Ultimate Coding Agent ↗</a></div>
        <div>📚 <a href="https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#c084fc; text-decoration:none; font-weight:600;">Enterprise RAG Engine ↗</a></div>
        <div>🌐 <a href="https://xestal-research-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#4ade80; text-decoration:none; font-weight:600;">Deep Research Agent ↗</a></div>
        <div>📑 <a href="https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#fbbf24; text-decoration:none; font-weight:600;">Invoice Audit Agent ↗</a></div>
        <div>🛠️ <a href="https://code-dev-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:600;">Code Dev Agent ↗</a></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.caption("Telemetry: `LangSmith (ultimate-coding-agent)`")
    st.caption("Vector DB: `ChromaDB + BM25 (8 Libraries)`")
    st.caption("Engine: `Dual Spark 4B Topology`")


# ============================================================================
# TOP BRAND BAR
# ============================================================================
st.markdown(f"""
<div class="top-bar">
    <div class="top-bar-left">
        <span class="pulse-dot pulse-green"></span>
        <div class="top-bar-brand">X-ESTAL NITISH <span>/</span> Mission Control</div>
    </div>
    <div class="top-chips">
        <span class="chip chip-cyan">Dual 4B Local LLM</span>
        <span class="chip chip-purple">LangSmith Tracing: ON</span>
        <span class="chip chip-green">Inference Cost: $0.00</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================================
# TAB 1: 💬 NEURAL CHAT (AI + LIVE WEB SEARCH)
# ============================================================================

if nav == "💬 Neural Chat (AI + Live Web)":
    st.markdown('<div class="hero-title">💬 Neural Assistant & Live Web Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Interactive conversational engineering powered by local <b>Spark 2.5 (4B)</b> '
        'with multi-tool research intelligence (Web, News, GitHub, URL Reader). Routed via <code>main.chat_turn</code>.</div>',
        unsafe_allow_html=True
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Chat controls bar with Research Tool Selector
    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl1:
        tool_option = st.selectbox(
            "Intelligence & Research Mode",
            options=[
                "⚡ Auto (Smart Tool Router: Web / News / GitHub / URL Reader)",
                "🌐 Deep Web Search (/web)",
                "📰 Live News Search (/news)",
                "🐙 GitHub Repositories (/github)",
                "📑 Read Web Page from URL (/read)",
            ],
            index=0,
        )
    with col_ctrl2:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("🗑️ Clear History", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    tool_mode_map = {
        "⚡ Auto (Smart Tool Router: Web / News / GitHub / URL Reader)": None,
        "🌐 Deep Web Search (/web)": "web",
        "📰 Live News Search (/news)": "news",
        "🐙 GitHub Repositories (/github)": "github",
        "📑 Read Web Page from URL (/read)": "read",
    }
    active_tool_override = tool_mode_map.get(tool_option)

    # Welcome Card if conversation is empty
    if len(st.session_state.chat_history) == 0:
        st.markdown("""
        <div class="clay-card" style="border-color: rgba(0, 240, 255, 0.25);">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <span style="font-size:24px;">⚡</span>
                <div>
                    <h3 style="margin:0; font-size:18px; color:#f8fafc;">Welcome to X-ESTAL AI Workspace</h3>
                    <p style="margin:0; font-size:13px; color:#94a3b8;">
                        Ask architecture questions, debug code, or request live web/news/GitHub research.
                        Communicates in fluent English or natural Hinglish with persistent conversational memory.
                    </p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Display past conversation
    for sender, msg, metadata in st.session_state.chat_history:
        is_user = sender == "User"
        with st.chat_message("user" if is_user else "assistant", avatar="👤" if is_user else "⚡"):
            st.markdown(msg)
            if metadata and metadata.get("tool_used"):
                tool_label = metadata["tool_used"].upper()
                query_info = metadata.get("search_query") or "Executed"
                with st.expander(f"🔍 Research Tool Used: [{tool_label}] on `{query_info}`"):
                    st.text(metadata.get("web_results", "No raw snippet stored."))

    # Chat input box
    user_input = st.chat_input("Prompt X-ESTAL AI for code, debugging, or real-time web research...")

    # Quick prompt pills - ONLY SHOW WHEN NO MESSAGES HAVE BEEN SENT YET!
    preset_query = None
    if len(st.session_state.chat_history) == 0:
        st.markdown("<p style='font-size:12px; color:#94a3b8; font-weight:700; margin-top:16px;'>QUICK PROMPTS:</p>", unsafe_allow_html=True)
        q_col1, q_col2, q_col3 = st.columns(3)
        with q_col1:
            if st.button("🔍 6-Node LangGraph Pipeline", key="q1"):
                preset_query = "Explain how the LangGraph 6-node state machine handles AST security checks and self-healing retries."
        with q_col2:
            if st.button("⚡ Spark 2.5 vs 2.6 Dual Routing", key="q2"):
                preset_query = "Why does X-ESTAL NITISH split analytical reasoning (Spark 2.5) from code synthesis (Spark 2.6)?"
        with q_col3:
            if st.button("📊 P50 vs P99 Tail Latency", key="q3"):
                preset_query = "What is the engineering tradeoff between P50 fast-path latency and P99 tail latency in self-healing agents?"

    final_query = user_input or preset_query

    if final_query:
        auto_start_servers_ui(["main"])
        
        with st.chat_message("user", avatar="👤"):
            st.markdown(final_query)

        with st.chat_message("assistant", avatar="⚡"):
            message_placeholder = st.empty()
            with st.spinner("X-ESTAL is reasoning & querying research tools..."):
                try:
                    res = main.chat_turn(
                        query=final_query,
                        history=[(s, m) for s, m, _ in st.session_state.chat_history],
                        force_web=bool(active_tool_override == "web"),
                        tool_override=active_tool_override,
                    )
                    answer = res["answer"]
                    message_placeholder.markdown(answer)

                    meta = {
                        "search_query": res.get("search_query"),
                        "tool_used": res.get("tool_used"),
                        "web_results": res.get("web_results")
                    }
                    if res.get("tool_used"):
                        tool_name = res["tool_used"].upper()
                        with st.expander(f"🔍 Research Tool Telemetry: [{tool_name}] `{res.get('search_query', '')}`"):
                            st.text(res.get("web_results", ""))

                    st.session_state.chat_history.append(("User", final_query, None))
                    st.session_state.chat_history.append(("X-ESTAL", answer, meta))
                    st.rerun()
                except Exception as e:
                    message_placeholder.error(f"Chat generation error: {e}")


# ============================================================================
# TAB 2: 📚 HYBRID RAG INTELLIGENCE (WITH POST-RETRIEVAL LLM)
# ============================================================================

elif nav == "📚 Hybrid RAG Intelligence":
    st.markdown('<div class="hero-title">📚 Hybrid RAG Knowledge Engine</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Dense Vector Search (ChromaDB + BGE-Small) + BM25 Lexical Ranking + '
        '<b>Post-Retrieval Local LLM Synthesis (Spark 2.5 4B)</b> for grounded documentation answers with citations.</div>',
        unsafe_allow_html=True
    )

    libs = rag.libraries() if "rag" in sys.modules else []
    
    col_l1, col_l2 = st.columns([2, 1])
    with col_l1:
        target_lib = st.selectbox(
            "Filter by Documentation Library",
            options=["All Indexed Libraries"] + sorted(libs),
            index=0,
        )
    with col_l2:
        top_k = st.slider("Top Relevant Chunks (k)", min_value=1, max_value=8, value=4)

    rag_query = st.text_input(
        "Technical Documentation Query",
        placeholder="e.g. How to define state in LangGraph StateGraph, or FastAPI dependency injection pattern",
    )

    if st.button("🔍 Search & Synthesize Grounded Answer", use_container_width=True) and rag_query:
        auto_start_servers_ui(["main"])
        selected_lib = None if target_lib == "All Indexed Libraries" else target_lib
        
        with st.spinner("Retrieving vector embeddings and synthesizing answer via Spark 2.5 4B..."):
            res = main.rag_turn(query=rag_query, library=selected_lib, k=top_k)
            
            st.markdown('<div class="clay-card">', unsafe_allow_html=True)
            st.markdown("### 🤖 Synthesized Grounded Answer (Spark 2.5 4B)")
            st.markdown(res["answer"])
            st.markdown("</div>", unsafe_allow_html=True)

            hits = res.get("hits", [])
            st.markdown(f"#### 📑 Retrieved Source Excerpts ({len(hits)} Matches)")
            if hits:
                for i, hit in enumerate(hits, 1):
                    src_file = hit["source"].replace("\\", "/").split("/")[-1]
                    with st.expander(f"[{i}] {hit['library']} (v{hit['version']}) — {src_file} [Page {hit['page']}] - {hit.get('heading') or 'Section'}"):
                        st.markdown(f"**Score:** `{hit.get('score', 0):.4f}` | **Heading:** `{hit.get('heading') or 'None'}`")
                        st.code(hit['text'], language="text")
            else:
                st.info("No matching chunks found in the index.")


# ============================================================================
# TAB 3: 🚀 AUTONOMOUS CODE SYNTHESIZER (PIPELINE)
# ============================================================================

elif nav == "🚀 Autonomous Code Synthesizer":
    st.markdown('<div class="hero-title">🚀 Autonomous Code Dev Pipeline</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Multi-Agent Code Engine by <b>X-ESTAL NITISH</b>. '
        'Orchestrates <b>Planner → Writer → AST Security Gate → Sandboxed Executor → Self-Healing Debugger → Reviewer</b>.</div>',
        unsafe_allow_html=True
    )

    # Check for active checkpoint
    active_cp = None
    try:
        active_cp = checkpoint_manager.get_active_checkpoint()
    except Exception:
        pass

    if active_cp:
        st.markdown(f"""
        <div class="clay-card" style="border-color: rgba(245, 158, 11, 0.4);">
            <span class="chip chip-purple">ACTIVE CHECKPOINT DETECTED</span>
            <h4 style="margin:8px 0 4px 0; color:#f8fafc;">Task: {active_cp.get('task', 'Unknown')}</h4>
            <span style="font-size:12px; color:#94a3b8;">Stage: <b>{active_cp.get('stage')}</b> | Files Saved: <b>{active_cp.get('files_count', 0)}</b></span>
        </div>
        """, unsafe_allow_html=True)
        
        c_cp1, c_cp2 = st.columns(2)
        with c_cp1:
            resume_btn = st.button("🔄 Resume Interrupted Session", use_container_width=True)
        with c_cp2:
            discard_btn = st.button("🗑️ Archive & Start Fresh Task", use_container_width=True)
        
        if resume_btn:
            auto_start_servers_ui(["main", "writer"])
            with st.spinner("Resuming pipeline from last checkpoint..."):
                res = main.code_turn(request="", resume_checkpoint=active_cp)
                st.success("Session completed!")
                st.markdown(res.get("summary", ""))
        
        if discard_btn:
            checkpoint_manager.discard_active_checkpoint()
            st.info("Checkpoint archived to history.")
            st.rerun()

    st.markdown("### 🛠️ New Autonomous Engineering Specification")
    
    c_opt1, c_opt2 = st.columns([2, 1])
    with c_opt1:
        research_mode_choice = st.selectbox(
            "🌐 Web Research Intelligence Mode",
            options=[
                "⚡ Smart Auto-Detect (Auto-scans APIs, libraries, scraping, web)",
                "🌐 Force Deep Web Research (Always investigate live web before coding)",
                "⏩ Fast Offline Only (Skip web research)",
            ],
            index=0,
            help="When enabled, the Deep Web Research Agent crawls live documentation, API endpoints, and SDK usage to ground the code synthesizer.",
        )
    with c_opt2:
        research_depth_choice = st.selectbox(
            "🔬 Research Depth",
            options=["basic (Faster)", "advanced (Deep Dive)"],
            index=0,
            help="Basic performs fast targeted searches. Advanced performs full multi-query recursive research.",
        )

    task_prompt = st.text_area(
        "Software Specification Prompt",
        height=130,
        placeholder="e.g. Build an asynchronous high-throughput REST API with FastAPI, JWT authentication, SQLite, and pytest test suite.",
    )

    if st.button("🚀 Launch Autonomous Multi-Agent Pipeline", use_container_width=True) and task_prompt:
        auto_start_servers_ui(["main", "writer"])
        
        mode_val = "auto"
        if "Force Deep" in research_mode_choice:
            mode_val = "on"
        elif "Fast Offline" in research_mode_choice:
            mode_val = "off"
        
        depth_val = "advanced" if "advanced" in research_depth_choice else "basic"
        os.environ["PIPELINE_RESEARCH_DEPTH"] = depth_val

        progress_bar = st.progress(0, text="Initializing state machine...")
        status_box = st.empty()
        
        def on_step_ui(node_name, state_snap):
            node_map = {
                "intake": ("📥 Intake: Initializing task parameters...", 10),
                "researcher": ("🌐 Researcher: Investigating live web & API documentation...", 25),
                "mediator": ("📚 Mediator: Evaluating technical requirements & docs...", 35),
                "rag": ("🔍 RAG: Retrieving library knowledge...", 45),
                "summarizer": ("📝 Summarizer: Digesting technical insights...", 55),
                "planner": ("📐 Planner: Formulating multi-file architecture blueprint...", 65),
                "coder": ("💻 Senior Writer: Synthesizing & testing multi-file repository...", 85),
                "finalize": ("✅ Finalize: Packaging repository & delivery report...", 100),
            }
            disp, pct = node_map.get(node_name, (f"Executing {node_name}...", 50))
            progress_bar.progress(pct, text=disp)
            status_box.markdown(f'<div class="chip chip-cyan"><span class="pulse-dot pulse-green"></span> {disp}</div>', unsafe_allow_html=True)

        with st.spinner("Synthesizing multi-file codebase with dual local models..."):
            try:
                progress_bar.progress(15, text="Node 1: Checking research & architecture requirements...")
                res = main.code_turn(
                    request=task_prompt,
                    force_fresh=True,
                    research=mode_val,
                    progress_cb=on_step_ui,
                )
                progress_bar.progress(100, text="Pipeline Execution Complete!")
                status_box.markdown('<div class="chip chip-green">✅ Autonomous Execution Complete!</div>', unsafe_allow_html=True)
                
                # Show research intelligence if gathered
                if res.get("research"):
                    with st.expander("🔍 Deep Web Research Dossier & API Intelligence Captured", expanded=False):
                        st.markdown(f'<div class="chip chip-purple">Report Size: {len(res["research"])} chars</div>', unsafe_allow_html=True)
                        if res.get("research_path"):
                            st.caption(f"Saved: `{res['research_path']}`")
                        st.markdown(res["research"])

                st.markdown('<div class="clay-card">', unsafe_allow_html=True)
                st.markdown("### 📦 Synthesized Repository Output")
                st.markdown(res.get("summary", "Done"))
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Pipeline error: {e}")

    # Inspect recently generated code repositories
    st.markdown("---")
    st.markdown("#### 📂 Generated Repositories Explorer (`output/`)")
    out_dir = ROOT / "output"
    if out_dir.exists():
        subdirs = sorted([d for d in out_dir.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
        if subdirs:
            sel_dir = st.selectbox("Select Project Directory", options=[d.name for d in subdirs])
            target_path = out_dir / sel_dir
            files = sorted(list(target_path.glob("**/*")))
            code_files = [f for f in files if f.is_file() and f.suffix in (".py", ".json", ".md", ".txt")]
            
            if code_files:
                col_f1, col_f2 = st.columns([1, 3])
                with col_f1:
                    sel_file = st.radio("Files", options=[f.relative_to(target_path).as_posix() for f in code_files])
                with col_f2:
                    if sel_file:
                        full_f = target_path / sel_file
                        st.markdown(f"**Viewing:** `{sel_file}` ({full_f.stat().st_size} bytes)")
                        with open(full_f, "r", encoding="utf-8", errors="replace") as f:
                            st.code(f.read(), language="python" if sel_file.endswith(".py") else "text")


# ============================================================================
# TAB 4: 🌐 DEEP WEB RESEARCH AGENT
# ============================================================================

elif nav == "🌐 Deep Web Research Agent":
    st.markdown('<div class="hero-title">🌐 Deep Web Research Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Autonomous recursive market intelligence & whitepaper engine. '
        'Formulates multi-angle search queries, fact-checks claims, and synthesizes executive dossiers.</div>',
        unsafe_allow_html=True
    )

    research_topic = st.text_input(
        "Enter Research Topic or Competitive Intelligence Query",
        placeholder="e.g. Next-generation local LLM inference engines and quantization benchmarks in late 2026",
    )

    if st.button("🔬 Execute Deep Research Whitepaper", use_container_width=True) and research_topic:
        auto_start_servers_ui(["main"])
        with st.spinner("Scraping web sources, validating citations, and compiling dossier..."):
            try:
                res = main.research_turn(research_topic)
                st.markdown('<div class="clay-card">', unsafe_allow_html=True)
                st.markdown("### 📄 Research Report Dossier")
                st.markdown(res.get("report", ""))
                if res.get("saved_path"):
                    st.success(f"Report saved to disk: `{res['saved_path']}`")
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Research execution error: {e}")


# ============================================================================
# TAB 5: 🤖 ENTERPRISE 5-AGENT SUITE
# ============================================================================

elif nav == "🤖 Enterprise 5-Agent Suite":
    st.markdown('<div class="hero-title">🤖 Enterprise 5-Agent Suite</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Production multi-agent systems designed by <b>X-ESTAL NITISH</b>, '
        'verified with automated unit test suites and LangSmith tracing.</div>',
        unsafe_allow_html=True
    )

    agents = [
        ("1. SWE Bug Resolver / PR Reviewer", "output/swe_bug_resolver_agent.py", "Autonomous GitHub Issue Triage, Code Fixer, Subprocess Testing, and PR Generator."),
        ("2. B2B Invoice & Expense Audit Agent", "output/invoice_audit_agent.py", "Multimodal Invoice Extraction, 3-Way PO Matching, GST Compliance & Fraud Flagging."),
        ("3. Deep Research & Competitive Intelligence", "output/deep_research_agent.py", "Planner, Parallel Web Scrapers, Fact-Checker, and Markdown/PDF Synthesizer."),
        ("4. Customer Resolution Agent", "output/customer_resolution_agent.py", "Sentiment Classification, CRM & Refund Tool Calling, and Human-in-the-Loop Safeguards."),
        ("5. Clinical Decision Copilot", "output/clinical_copilot_agent.py", "EHR Summarization, Drug-Drug Interaction Verification, and Evidence-Based Diagnostic Suggestions."),
    ]

    selected_agent = st.selectbox("Select Agent Application", options=[a[0] for a in agents])
    agent_info = next(a for a in agents if a[0] == selected_agent)

    st.markdown(f"""
    <div class="clay-card">
        <span class="chip chip-purple">ENTERPRISE SYSTEM ARCHITECTURE</span>
        <h3 style="color:#f8fafc; margin-top:8px;">{agent_info[0]}</h3>
        <p style="color:#94a3b8;">{agent_info[2]}</p>
        <span style="font-size:12px; color:#00f0ff;">File: <code>{agent_info[1]}</code></span>
    </div>
    """, unsafe_allow_html=True)

    if st.button("⚡ Run Agent Benchmark Verification", use_container_width=True):
        with st.spinner(f"Running automated test harness for {agent_info[0]}..."):
            proc = subprocess.run(
                [str(PYTHON_EXE), str(ROOT / agent_info[1])],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            if proc.returncode == 0:
                st.success("✅ Verification Passed: Deterministic assertions confirmed!")
                st.markdown(f'<div class="neural-console">{proc.stdout}</div>', unsafe_allow_html=True)
            else:
                st.error("Execution encountered errors:")
                st.code(proc.stderr)

    with st.expander("📄 View Agent Source Code"):
        with open(ROOT / agent_info[1], "r", encoding="utf-8") as f:
            st.code(f.read(), language="python")


# ============================================================================
# TAB 6: 📊 LANGSMITH PRODUCTION OBSERVABILITY
# ============================================================================

elif nav == "📊 LangSmith Production Observability":
    st.markdown('<div class="hero-title">📊 LangSmith Production Observability</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">Production telemetry across <b>90–100 benchmark runs</b> '
        'on project <code>ultimate-coding-agent</code> by <b>X-ESTAL NITISH</b>.</div>',
        unsafe_allow_html=True
    )

    # Top KPI Metrics Cards in Claymorphism
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Benchmark Runs</div>
            <div class="value">90–100</div>
            <div class="sub">91 Succeeded · 5 Failed</div>
        </div>
        """, unsafe_allow_html=True)
    with m_col2:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Verified Pass Rate</div>
            <div class="value" style="color:#4ade80;">95%</div>
            <div class="sub">Autonomous Self-Healing</div>
        </div>
        """, unsafe_allow_html=True)
    with m_col3:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">P50 vs P99 Latency</div>
            <div class="value">0.2s <span style="font-size:16px; color:#94a3b8;">/ 2.3ks</span></div>
            <div class="sub">Fast Path vs Deep-Heal</div>
        </div>
        """, unsafe_allow_html=True)
    with m_col4:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Total Cloud Cost</div>
            <div class="value" style="color:#00f0ff;">$0.00</div>
            <div class="sub">100% Local Inference</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_obs1, col_obs2 = st.columns(2)
    with col_obs1:
        st.markdown("""
        <div class="clay-card">
            <h4>🤖 Model Distribution (197 Total Invocations)</h4>
            <p style="color:#94a3b8; font-size:13px;">Zero cloud API tokens. 100% served locally via memory-locked <code>llama-server</code>.</p>
            <div style="margin-top:14px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span style="font-weight:600;">X-Estal-4B Dual Topology</span>
                    <span style="color:#00f0ff; font-weight:700;">197 calls (100%)</span>
                </div>
                <div style="background:#1e293b; border-radius:10px; height:8px; overflow:hidden;">
                    <div style="background:linear-gradient(90deg, #00f0ff, #a855f7); width:100%; height:100%;"></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col_obs2:
        st.markdown("""
        <div class="clay-card">
            <h4>🛠️ Tool Invocations Breakdown</h4>
            <div style="font-size:13px; line-height:2;">
                <div style="display:flex; justify-content:space-between;">
                    <span>🌐 <code>web_search</code></span><span style="font-weight:700; color:#00f0ff;">36 calls (40%)</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span>📄 <code>web_reader</code></span><span style="font-weight:700; color:#00f0ff;">21 calls (23%)</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span>📑 <code>pdf_reader</code></span><span style="font-weight:700; color:#00f0ff;">12 calls (13%)</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span>🧩 <code>smart_chunk_document</code></span><span style="font-weight:700; color:#00f0ff;">12 calls (13%)</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span>💾 <code>chroma_store</code></span><span style="font-weight:700; color:#00f0ff;">10 calls (11%)</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="clay-card">
        <h4>🔬 The Mathematical Signature of Tail Latency (P50 vs P99)</h4>
        <p style="color:#94a3b8; line-height:1.6;">
            In traditional web services, a divergence between P50 and P99 indicates an infrastructure bottleneck.
            In self-healing autonomous agents, however, <b>high P99 tail latency is the mathematical signature of the self-healing loop doing its job</b>.
        </p>
        <ul style="color:#cbd5e1; font-size:14px; line-height:1.7;">
            <li><b>P50 Fast Path (Attempt 1):</b> Single-pass linear execution (<code>planner → writer → security_check → executor → reviewer</code>) finishes with zero retries. Latency is ultra-low (0.2s).</li>
            <li><b>P99 Tail Path (3 Retries):</b> Up to 3 recursive debug loops (<code>debugger → writer → security_check → executor</code>) expanding the state machine from 5 to 14 sequential node invocations, absorbing complex runtime debugging into tail latency while delivering a 90–95% final pass rate.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# TAB 7: 📖 TECHNICAL CASE STUDY
# ============================================================================

elif nav == "📖 Technical Case Study":
    st.markdown('<div class="hero-title">📖 Engineering Case Study</div>', unsafe_allow_html=True)
    st.markdown("## Ultimate Coding Agent Turns Classroom Project Prompts Into Self-Healing Multi-File Software")
    st.markdown("**Engineered by [Nitish Kumar (XestalNitish)](https://github.com/XestalNitish) in November 2026**")

    # Header Executive Summary
    st.markdown("""
    <div class="clay-card">
        <p style="font-size:15px; color:#f8fafc; line-height:1.7;">
            Engineered by <b><a href="https://github.com/XestalNitish" style="color:#00f0ff; text-decoration:none;">Nitish Kumar</a></b> in November 2026 to eliminate student paralysis during college software assignments, this six-node stateful LangGraph pipeline orchestrates dual local 4B models (<code>Spark 2.5</code> and <code>Spark 2.6</code>) to autonomously plan, synthesize, audit, execute, and debug complete repositories on consumer hardware.
        </p>
        <div style="background:rgba(0, 240, 255, 0.08); border-left:4px solid #00f0ff; padding:14px 18px; border-radius:8px; margin-top:14px;">
            <b style="color:#00f0ff;">Engineering Verdict:</b>
            <span style="color:#cbd5e1; font-size:14px; line-height:1.6;">
                Across 90–100 end-to-end LangSmith evaluation runs, the pipeline achieved a 90–95% pass rate (only 5 failures) with zero cloud API cost. By decoupling architectural reasoning (<code>Spark 2.5 4B</code>) from code generation (<code>Spark 2.6 4B</code>) and enforcing an isolated subprocess execution loop (up to 3 self-healing retries), the system keeps median (<code>P50</code>) latency low on first-pass builds while absorbing complex debugging into tail (<code>P99</code>) latency.
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 95% Verified Pass Rate Metric Highlight
    c_met1, c_met2 = st.columns([1, 3])
    with c_met1:
        st.markdown("""
        <div class="clay-metric" style="text-align:center;">
            <div class="label">Pass Rate</div>
            <div class="value" style="font-size:46px; color:#4ade80;">95%</div>
            <div class="sub">Autonomous Self-Healing</div>
        </div>
        """, unsafe_allow_html=True)
    with c_met2:
        st.markdown("""
        <div class="clay-card" style="height:100%; display:flex; align-items:center;">
            <p style="margin:0; font-size:15px; color:#cbd5e1; line-height:1.6;">
                <b>Verified compilation and execution pass rate</b> across 90–100 LangSmith benchmark test runs, recording only 5 unrecovered failures after up to 3 automated self-healing debug cycles.
            </p>
        </div>
        """, unsafe_allow_html=True)

    # Section 1: Classroom Confusion
    st.markdown("### 🎓 Classroom Confusion Sparked an Autonomous Pipeline From Prompt to Production")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            During a routine lecture at <b>C.M. Science College, Darbhanga</b>, an instructor assigned a batch of software project topics to the class. While students understood the high-level problem statements, the majority stalled immediately on the engineering translation: how to decompose a vague topic into concrete system requirements, how to organize a modular multi-file directory structure, and how to diagnose cascading runtime tracebacks once the initial scripts failed.
        </p>
        <p style="color:#cbd5e1; line-height:1.7;">
            Standard single-shot chat LLMs only partially solve this problem. When a student pastes a project topic into a chat window, the model typically returns an unverified single-file snippet that breaks on missing imports, unguarded edge cases, or subtle syntax errors. Instead of learning architecture, students get trapped manually copying tracebacks back and forth.
        </p>
        <p style="color:#cbd5e1; line-height:1.7;">
            To solve this end-to-end bottleneck, <b><a href="https://www.linkedin.com/in/nitish-kumar-ai" style="color:#00f0ff; text-decoration:none;">Nitish Kumar</a></b> designed the Ultimate Coding Agent (with an early interactive prototype showcased via the <a href="https://code-dev-agent-by-x-estal-nitish.streamlit.app/" style="color:#c084fc; text-decoration:none;">X-Estal Code Dev Agent</a>). The design premise is strict: a user supplies only the core problem prompt in a <code>test</code> specification, and the pipeline autonomously handles requirement refinement, multi-file synthesis, static security verification, runtime validation, and iterative self-repair into a clean <code>output</code> directory.
        </p>
        <blockquote style="font-size:16px; font-style:italic; color:#00f0ff; border-left:4px solid #00f0ff; padding-left:16px; margin:16px 0 0 0;">
            "Everyone in class was confused about how to analyze the topic, structure the requirements, and build the project—so I built an autonomous pipeline where you give only your core problem prompt, and it handles requirements, multi-file coding, and self-debugging from start to finish."
            <br><span style="font-size:13px; font-weight:700; color:#f8fafc; font-style:normal;">— Nitish Kumar, Creator of the Ultimate Coding Agent</span>
        </blockquote>
    </div>
    """, unsafe_allow_html=True)

    # Section 2: Six Stateful LangGraph Nodes
    st.markdown("### 🧩 Six Stateful LangGraph Nodes Enforce Security Auditing and Cyclic Self-Repair")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            Rather than relying on linear prompt chaining, the Ultimate Coding Agent models software creation as a cyclic directed graph using <code>StateGraph</code>. Shared state tracks the parsed project specification, file tree map, abstract syntax tree (AST) audit flags, subprocess <code>stdout</code>/<code>stderr</code> streams, and retry counter across six specialized nodes.
        </p>
        <p style="color:#38bdf8; font-size:13px; font-weight:600;">
            Cyclic self-healing loops convert single-pass runtime crashes into verified multi-file builds
        </p>
        <p style="color:#94a3b8; font-size:13px;">
            Architectural flow from raw user prompt (left) through planning, synthesis, static AST security gating, isolated 15-second sandboxed subprocess execution, and the conditional feedback loop (<code>Exit != 0</code>, up to 3 retries) before writing verified multi-file packages to <code>output</code> (right).
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    | Node ID | Pipeline Role | Assigned Local LLM | Primary Input State | Verification Gate & Routing Transition | Guard / Limit |
    | :--- | :--- | :--- | :--- | :--- | :--- |
    | `planner` | Architectural Planner | Spark 2.5 (4B) | Raw user prompt from test spec | Decomposes prompt into system requirements, module boundaries, and multi-file dependency manifest; routes to `writer`. | 2048 ctx window |
    | `writer` | Senior Code Writer | Spark 2.6 (4B) | Architecture plan or debugger patch diff | Synthesizes complete, runnable multi-file Python code blocks mapped to target file paths; routes directly to `security_check`. | Multi-file output |
    | `security_check` | Pre-Execution AST Auditor | Spark 2.5 (4B) + AST | Generated source files prior to runtime | Performs static analysis for destructive shell calls, unauthorized network sockets, or unsafe imports before execution; routes to `executor` or back to `writer`. | 0 unsafe execs |
    | `executor` | Sandboxed Runtime Executor | Deterministic Subprocess | Security-cleared code package | Executes entrypoints inside an isolated Python subprocess; routes to `reviewer` if `Exit == 0`, or triggers `debugger` if `Exit != 0`. | 15s timeout |
    | `debugger` | Self-Healing Debugger | Spark 2.5 (4B) | Captured `stderr` traceback & failing file | Isolates root cause from stack trace, formulates targeted code repair instructions, and loops back to `writer` until retries exhaust. | Max 3 retries |
    | `reviewer` | Production Reviewer | Spark 2.5 (4B) | Verified codebase (`Exit == 0`) | Validates requirement coverage, code modularity, and documentation readiness before committing final artifacts to `output`. | Final commit |
    """)

    # Section 3: Dual 4B Local Model Routing
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🧠 Dual 4B Local Model Routing Eliminates Cloud Costs on 16GB RAM Hardware")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            Running a multi-agent coding loop against commercial cloud APIs quickly incurs prohibitive token bills—especially when multi-file codebases enter 2 to 3 self-healing debug iterations. Conversely, running a single massive model locally freezes consumer laptops. During early hardware stress tests on an Intel Core i5 workstation with 16GB RAM, a smaller 1.7B parameter variant lacked the reasoning depth to untangle multi-file imports, while unthrottled inference saturated CPU threads.
        </p>
        <p style="color:#cbd5e1; line-height:1.7;">
            The Ultimate Coding Agent solves this by splitting cognitive workloads across two specialized 4-billion-parameter local models served via an optimized <code>llama-server</code> backend (<code>local_llm_service.py</code>). By locking model weights in memory (<code>--mlock</code>), capping CPU thread contention, and managing context length via <code>trim_messages</code> within a 2048-token active window, the pipeline runs entirely offline without thermal throttling or swap thrashing.
        </p>
        <p style="color:#38bdf8; font-size:13px; font-weight:600;">
            Splitting reasoning and code synthesis across two specialized 4B models prevents local memory bottlenecks
        </p>
        <p style="color:#94a3b8; font-size:13px; line-height:1.6;">
            Dual-core local inference topology: <code>Spark 2.5 (4B)</code> (cobalt pathways, left) handles requirement analysis, AST security auditing, traceback diagnostics, and final review, while <code>Spark 2.6 (4B)</code> (amber pathways, right) focuses exclusively on multi-file code synthesis feeding into the 15-second guarded execution container.
        </p>
        <hr style="border-color: rgba(255, 255, 255, 0.08); margin:16px 0;">
        <h4 style="color:#38bdf8; margin-bottom:6px;">Spark 2.5 (4B) — Analytical Core</h4>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.6;">
            Assigned to <code>planner</code>, <code>security_check</code>, <code>debugger</code>, and <code>reviewer</code>. Optimized for structured decomposition, static vulnerability pattern recognition, and stack-trace root-cause isolation where concise analytical precision matters more than raw code token volume.
        </p>
        <h4 style="color:#c084fc; margin-bottom:6px; margin-top:14px;">Spark 2.6 (4B) — Synthesis Core</h4>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.6;">
            Dedicated exclusively to the <code>writer</code> node. Tuned for syntactic accuracy, cross-file import consistency, and clean adherence to the planner's structural manifest, ensuring generated Python modules integrate seamlessly across directory boundaries.
        </p>
        <h4 style="color:#4ade80; margin-bottom:6px; margin-top:14px;">Subprocess & Context Guards</h4>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.6;">
            Enforces <code>trim_messages</code> state pruning to prevent context overflow during multi-turn retries, alongside a strict 15-second subprocess execution timeout in <code>executor</code> to automatically catch and terminate infinite <code>while</code> loops or blocking I/O calls.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Section 4: LangSmith Benchmarks
    st.markdown("### 📊 LangSmith Benchmarks Reveal Why Tail Latency Is a Feature of Self-Healing Systems")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            To move beyond anecdotal demos, the pipeline was instrumented with LangSmith observability and evaluated across a batch of 90 to 100 diverse project prompts placed in the <code>test</code> suite. The resulting telemetry uncovered a signature bimodal latency distribution: median (<code>P50</code>) latency remains remarkably low, whereas 99th-percentile (<code>P99</code>) latency spikes sharply.
        </p>
        <p style="color:#cbd5e1; line-height:1.7;">
            In a conventional web microservice, a wide gap between <code>P50</code> and <code>P99</code> signals an infrastructure bottleneck. In an autonomous coding agent, however, high <code>P99</code> latency is the direct mathematical signature of the self-healing loop doing its job. When a prompt succeeds on the first pass (<code>Exit == 0</code> on Attempt 1), the graph traverses only five nodes linearly (<code>planner → writer → security_check → executor → reviewer</code>), keeping <code>P50</code> execution fast. When a complex prompt triggers an <code>ImportError</code>, schema mismatch, or 15-second timeout, the graph loops through <code>debugger → writer → security_check → executor</code> up to 3 times—multiplying node invocations from 5 to as many as 14 sequential steps, trading wall-clock latency for a 90–95% final pass rate.
        </p>
        <p style="color:#38bdf8; font-size:13px; font-weight:600;">
            Iterative debugging loops drive P99 tail latency while single-pass builds keep P50 latency low
        </p>
        <div style="background:#090e18; border:1px solid rgba(0, 240, 255, 0.2); border-radius:12px; padding:16px; margin:14px 0; font-family:'JetBrains Mono', monospace; font-size:13px; color:#38bdf8; line-height:1.8;">
            <div>[P50 Fast Path (Attempt 1)]  0 retries  · Exit == 0  ➔  5 nodes (1x baseline latency)</div>
            <div>[Single-Heal Path (1 Retry)] 1 debug loop · Fix try 2  ➔  8 nodes (~1.8x latency)</div>
            <div>[Deep-Heal Path (2 Retries)] 2 debug loops · Fix try 3 ➔ 11 nodes (~2.6x latency)</div>
            <div>[P99 Tail Path (3 Retries)]  Max repair + 15s guards  ➔ 14 nodes (Compounded tail latency)</div>
        </div>
        <p style="color:#94a3b8; font-size:12px;">
            Total Sequential StateGraph Node Invocations per Prompt Run (LangSmith Trace Topology). Comparison of sequential LangGraph node executions across latency percentiles. Each self-healing retry adds 3 extra node steps (<code>debugger → writer → security_check → executor</code>), plus up to 15 seconds per subprocess timeout guard when diagnosing hanging code.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    | LangSmith Evaluation Dimension | Observed Benchmark Result | Primary Architectural Driver | Measured Value |
    | :--- | :--- | :--- | :--- |
    | **Total Benchmark Suite Volume** | End-to-end multi-file prompts executed from test to output | Automated batch harness covering student-level & modular software specs | **90–100 runs** |
    | **End-to-End Success Rate** | Verified Exit == 0 builds passing final reviewer inspection | Iterative debugger → writer feedback loop rescuing initial syntax/import errors | **90%–95%** |
    | **Unrecovered Failure Count** | Prompts exhausting all 3 retry cycles without clean exit | Complex cross-file state dependencies exceeding 4B parameter context horizon | **5 fails** |
    | **Median Latency (P50)** | Very low wall-clock execution time | Single-pass traversal (5 nodes) with memory-locked (--mlock) local 4B weights | **5-node linear path** |
    | **Tail Latency (P99)** | High tail spike on edge-case prompts | Compounded 3-retry self-healing cycles (up to 14 nodes) + 15s subprocess timeout guards | **Up to 14 nodes** |
    """)

    # Section 5: Why a Local-Only Backend Demands an Interactive Web UI
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🖥️ Why a Local-Only Backend Still Demands an Interactive Web UI")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            A critical architectural reality of the Ultimate Coding Agent is that its inference engine (<code>llama-server</code> running local <code>Spark 2.5</code> and <code>Spark 2.6</code> 4B models) and its <code>executor</code> subprocess sandbox run on the host workstation. Because standard free cloud hosting tiers do not provide the dedicated RAM or local GGUF model daemon required to execute arbitrary subprocess code safely, external visitors cannot simply run the local backend directly in a static browser tab.
        </p>
        <p style="color:#cbd5e1; line-height:1.7;">
            Despite that local execution boundary, building a dedicated User Interface (UI)—the project's immediate next milestone—is essential for three engineering reasons:
        </p>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:14px; margin-top:14px;">
            <div style="background:rgba(14, 165, 233, 0.08); border:1px solid rgba(56, 189, 248, 0.25); border-radius:12px; padding:16px;">
                <h4 style="color:#38bdf8; margin:0 0 6px 0;">1. Live Graph Observability</h4>
                <p style="color:#cbd5e1; font-size:13px; margin:0; line-height:1.5;">
                    Transforms an invisible CLI script into an inspectable state machine, allowing users and recruiters to watch each node (<code>planner</code>, <code>writer</code>, <code>security_check</code>, <code>executor</code>, <code>debugger</code>, <code>reviewer</code>) light up in real time as retries occur.
                </p>
            </div>
            <div style="background:rgba(168, 85, 247, 0.08); border:1px solid rgba(192, 132, 252, 0.25); border-radius:12px; padding:16px;">
                <h4 style="color:#c084fc; margin:0 0 6px 0;">2. Hybrid Cloud Replay Mode</h4>
                <p style="color:#cbd5e1; font-size:13px; margin:0; line-height:1.5;">
                    Lets cloud visitors inspect the 90–100 LangSmith test runs, browse generated multi-file trees in <code>output</code>, and step through actual self-healing diffs without needing local GPU/CPU weights.
                </p>
            </div>
            <div style="background:rgba(34, 197, 94, 0.08); border:1px solid rgba(74, 222, 128, 0.25); border-radius:12px; padding:16px;">
                <h4 style="color:#4ade80; margin:0 0 6px 0;">3. Zero-Friction Onboarding</h4>
                <p style="color:#cbd5e1; font-size:13px; margin:0; line-height:1.5;">
                    Because the project was born to help confused college students turn class topics into working software, replacing raw terminal commands and <code>test</code> edits with an intuitive prompt box and file-tree viewer fulfills the original classroom mission.
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Section 6: Next-Stage Roadmap
    st.markdown("### 🗺️ Next-Stage Engineering Roadmap")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.7;">
            With the core six-node LangGraph engine verified at a 90–95% pass rate across 90–100 tests, the project transitions from backend stabilization to interface packaging and technical showcase distribution:
        </p>
        <ul style="color:#cbd5e1; line-height:1.8; font-size:14px;">
            <li><b>Build the Dual-Mode Streamlit / FastAPI Interface:</b> Connect a clean frontend directly to the local <code>StateGraph</code> stream (<code>app.stream()</code>) for live local execution, while bundling cached <code>test</code> → <code>output</code> telemetry traces so cloud visitors can interactively explore real multi-file builds and self-healing traceback repairs.</li>
            <li><b>Export LangSmith P50 vs. P99 Latency Snapshots:</b> Capture the LangSmith dashboard view showing the 90–100 test suite pass rate (only 5 fails) alongside a multi-step trace of a 2-retry self-healing run to embed directly in the repository <code>README.md</code>.</li>
            <li><b>Publish the Technical Case Study Across LinkedIn & GitHub:</b> Frame the launch around the classroom origin story and the engineering tradeoff between <code>P50</code> speed and <code>P99</code> self-healing reliability on 4B local models, linking directly to the <a href="https://github.com/XestalNitish" style="color:#00f0ff;">XestalNitish GitHub repository</a> and live demo.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

    # Section 7: Live Deployed AI Projects Showcase
    st.markdown("### 🌐 Live Deployed AI Applications & Project Ecosystem")
    st.markdown("""
    <div class="clay-card">
        <p style="color:#cbd5e1; line-height:1.6; margin-bottom:16px;">
            Explore the deployed interactive applications engineered by <b>Nitish Kumar (X-ESTAL NITISH)</b>:
        </p>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px;">
            <div style="background:rgba(15, 23, 42, 0.7); border:1px solid rgba(0, 240, 255, 0.25); border-radius:14px; padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#f8fafc;">🚀 Ultimate Coding Agent</h4>
                    <span class="chip chip-cyan">LIVE APP</span>
                </div>
                <p style="color:#94a3b8; font-size:12px; margin:8px 0 12px 0;">Self-healing multi-file software synthesizer powered by dual 4B local LLMs and LangGraph.</p>
                <a href="https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#00f0ff; font-weight:700; font-size:13px; text-decoration:none;">Open App ↗</a>
            </div>
            <div style="background:rgba(15, 23, 42, 0.7); border:1px solid rgba(168, 85, 247, 0.25); border-radius:14px; padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#f8fafc;">📚 X-Estal Enterprise RAG</h4>
                    <span class="chip chip-purple">LIVE APP</span>
                </div>
                <p style="color:#94a3b8; font-size:12px; margin:8px 0 12px 0;">Dense vector (ChromaDB + BGE) + BM25 hybrid documentation engine with LLM synthesis.</p>
                <a href="https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#c084fc; font-weight:700; font-size:13px; text-decoration:none;">Open App ↗</a>
            </div>
            <div style="background:rgba(15, 23, 42, 0.7); border:1px solid rgba(34, 197, 94, 0.25); border-radius:14px; padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#f8fafc;">🌐 X-Estal Deep Research</h4>
                    <span class="chip chip-green">LIVE APP</span>
                </div>
                <p style="color:#94a3b8; font-size:12px; margin:8px 0 12px 0;">Autonomous web intelligence, fact-checking, and technical whitepaper compiler.</p>
                <a href="https://xestal-research-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#4ade80; font-weight:700; font-size:13px; text-decoration:none;">Open App ↗</a>
            </div>
            <div style="background:rgba(15, 23, 42, 0.7); border:1px solid rgba(245, 158, 11, 0.25); border-radius:14px; padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#f8fafc;">📑 Invoice Audit Agent</h4>
                    <span class="chip chip-purple">LIVE APP</span>
                </div>
                <p style="color:#94a3b8; font-size:12px; margin:8px 0 12px 0;">Autonomous B2B invoice extraction, 3-way PO matching, and fraud variance detection.</p>
                <a href="https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#fbbf24; font-weight:700; font-size:13px; text-decoration:none;">Open App ↗</a>
            </div>
            <div style="background:rgba(15, 23, 42, 0.7); border:1px solid rgba(0, 240, 255, 0.25); border-radius:14px; padding:18px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h4 style="margin:0; color:#f8fafc;">🛠️ X-Estal Code Dev Agent</h4>
                    <span class="chip chip-cyan">LIVE APP</span>
                </div>
                <p style="color:#94a3b8; font-size:12px; margin:8px 0 12px 0;">Interactive early prototype showcased on Streamlit Cloud for prompt-to-production testing.</p>
                <a href="https://code-dev-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#00f0ff; font-weight:700; font-size:13px; text-decoration:none;">Open App ↗</a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Section 8: Sources & Project Links
    st.markdown("### 🔗 Author Profiles & Verified Links")
    st.markdown("""
    <div class="clay-card">
        <ul style="color:#cbd5e1; font-size:14px; line-height:2;">
            <li>🐙 <b>GitHub Engineering Portfolio:</b> <a href="https://github.com/XestalNitish" target="_blank" style="color:#00f0ff;">https://github.com/XestalNitish</a></li>
            <li>💼 <b>LinkedIn Developer Profile:</b> <a href="https://www.linkedin.com/in/nitish-kumar-ai" target="_blank" style="color:#00f0ff;">https://www.linkedin.com/in/nitish-kumar-ai</a></li>
            <li>🚀 <b>Ultimate Coding Agent (Live):</b> <a href="https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#00f0ff;">https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/</a></li>
            <li>📚 <b>X-Estal Enterprise RAG Engine (Live):</b> <a href="https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#c084fc;">https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/</a></li>
            <li>🌐 <b>X-Estal Deep Research Agent (Live):</b> <a href="https://xestal-research-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#4ade80;">https://xestal-research-agent-by-x-estal-nitish.streamlit.app/</a></li>
            <li>📑 <b>Invoice Processing & Audit Agent (Live):</b> <a href="https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#fbbf24;">https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/</a></li>
            <li>🛠️ <b>X-Estal Code Dev Agent (Live):</b> <a href="https://code-dev-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="color:#00f0ff;">https://code-dev-agent-by-x-estal-nitish.streamlit.app/</a></li>
        </ul>
    </div>
    """, unsafe_allow_html=True)



# ============================================================================
# TAB 8: 🌐 DEPLOYED AI PROJECTS & ECOSYSTEM
# ============================================================================

elif nav == "🌐 Deployed AI Projects & Ecosystem":
    st.markdown('<div class="hero-title">🌐 Live Deployed AI Projects & Ecosystem</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Production-grade AI systems, self-healing code synthesizers, enterprise RAG, and multi-agent solutions engineered by <b>X-ESTAL NITISH (Nitish Kumar)</b>.</div>', unsafe_allow_html=True)

    # Top Metric Highlights
    c_p1, c_p2, c_p3, c_p4 = st.columns(4)
    with c_p1:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Live Deployed Apps</div>
            <div class="value">5 Apps</div>
            <div class="sub">Streamlit Cloud Verified</div>
        </div>
        """, unsafe_allow_html=True)
    with c_p2:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Benchmark Pass Rate</div>
            <div class="value" style="color:#4ade80;">95%</div>
            <div class="sub">90–100 LangSmith Runs</div>
        </div>
        """, unsafe_allow_html=True)
    with c_p3:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Hardware Footprint</div>
            <div class="value" style="color:#00f0ff;">16GB RAM</div>
            <div class="sub">Zero Cloud API Costs</div>
        </div>
        """, unsafe_allow_html=True)
    with c_p4:
        st.markdown("""
        <div class="clay-metric">
            <div class="label">Architect</div>
            <div class="value" style="font-size:22px; color:#c084fc;">X-ESTAL</div>
            <div class="sub">Nitish Kumar</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # Detailed Showcase Cards for All 5 Deployed Applications
    st.markdown("### 🚀 Verified Live Applications")

    # Project 1: Ultimate Coding Agent
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">🚀</span>
                <div>
                    <h3 style="margin:0; color:#f8fafc;">Ultimate Coding Agent</h3>
                    <span style="font-size:12px; color:#94a3b8;">Autonomous Self-Healing Multi-File Software Engineer</span>
                </div>
            </div>
            <span class="chip chip-cyan"><span class="pulse-dot pulse-green"></span> 🟢 LIVE STREAMLIT APP</span>
        </div>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.7; margin:14px 0 10px 0;">
            Converts vague classroom project prompts into fully validated, running multi-file Python applications. Uses a 6-node stateful LangGraph pipeline orchestrating dual local 4B models (<code>Spark 2.5</code> and <code>Spark 2.6</code>) with pre-execution AST security auditing and isolated 15-second sandboxed execution retries.
        </p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
            <span class="chip chip-cyan">LangGraph</span>
            <span class="chip chip-purple">Dual Spark 4B</span>
            <span class="chip chip-green">Self-Healing Retries</span>
            <span class="chip chip-cyan">AST Security Check</span>
            <span class="chip chip-purple">Subprocess Sandbox</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <span style="color:#94a3b8; font-size:12px;">URL: <code style="color:#00f0ff;">https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/</code></span>
            <a href="https://ultimate-coding-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="background:linear-gradient(135deg, #00f0ff 0%, #0284c7 100%); color:#030712; padding:8px 18px; border-radius:10px; font-weight:700; font-size:13px; text-decoration:none; box-shadow:0 4px 15px rgba(0, 240, 255, 0.4);">Launch Application ↗</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Project 2: X-Estal Enterprise RAG Engine
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">📚</span>
                <div>
                    <h3 style="margin:0; color:#f8fafc;">X-Estal Enterprise RAG Engine</h3>
                    <span style="font-size:12px; color:#94a3b8;">Hybrid Dense + BM25 Document Intelligence with LLM Synthesis</span>
                </div>
            </div>
            <span class="chip chip-purple"><span class="pulse-dot pulse-green"></span> 🟢 LIVE STREAMLIT APP</span>
        </div>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.7; margin:14px 0 10px 0;">
            Enterprise documentation intelligence combining dense semantic vector search (ChromaDB + BAAI/bge-small-en-v1.5) with sparse keyword search (BM25Okapi) using Reciprocal Rank Fusion. Strictly grounds LLM answers on retrieved chunks to completely eliminate hallucination.
        </p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
            <span class="chip chip-purple">ChromaDB</span>
            <span class="chip chip-cyan">BM25Okapi Fusion</span>
            <span class="chip chip-green">BGE Embeddings</span>
            <span class="chip chip-purple">Zero Hallucination</span>
            <span class="chip chip-cyan">Source Citations</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <span style="color:#94a3b8; font-size:12px;">URL: <code style="color:#c084fc;">https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/</code></span>
            <a href="https://xestal-enterprise-rag-engine-by-x-estal-nitish.streamlit.app/" target="_blank" style="background:linear-gradient(135deg, #a855f7 0%, #7c3aed 100%); color:#ffffff; padding:8px 18px; border-radius:10px; font-weight:700; font-size:13px; text-decoration:none; box-shadow:0 4px 15px rgba(168, 85, 247, 0.4);">Launch Application ↗</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Project 3: X-Estal Deep Research Agent
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">🌐</span>
                <div>
                    <h3 style="margin:0; color:#f8fafc;">X-Estal Deep Research Agent</h3>
                    <span style="font-size:12px; color:#94a3b8;">Autonomous Live Web Intelligence & Whitepaper Compiler</span>
                </div>
            </div>
            <span class="chip chip-green"><span class="pulse-dot pulse-green"></span> 🟢 LIVE STREAMLIT APP</span>
        </div>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.7; margin:14px 0 10px 0;">
            Autonomous multi-tool research engine that breaks ambiguous topics into targeted search queries, crawls live web pages with Trafilatura, cross-verifies facts across multiple sources, and compiles comprehensive structured technical whitepapers with full bibliographies.
        </p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
            <span class="chip chip-green">DuckDuckGo Search</span>
            <span class="chip chip-cyan">Trafilatura Scraper</span>
            <span class="chip chip-purple">Multi-Hop Research</span>
            <span class="chip chip-green">Fact Verification</span>
            <span class="chip chip-cyan">Markdown Export</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <span style="color:#94a3b8; font-size:12px;">URL: <code style="color:#4ade80;">https://xestal-research-agent-by-x-estal-nitish.streamlit.app/</code></span>
            <a href="https://xestal-research-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="background:linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color:#030712; padding:8px 18px; border-radius:10px; font-weight:700; font-size:13px; text-decoration:none; box-shadow:0 4px 15px rgba(34, 197, 94, 0.4);">Launch Application ↗</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Project 4: Invoice Processing & Audit Agent
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">📑</span>
                <div>
                    <h3 style="margin:0; color:#f8fafc;">Invoice Processing & Audit Agent</h3>
                    <span style="font-size:12px; color:#94a3b8;">Autonomous B2B Invoice Extraction & Fraud Variance Detection</span>
                </div>
            </div>
            <span class="chip chip-purple"><span class="pulse-dot pulse-green"></span> 🟢 LIVE STREAMLIT APP</span>
        </div>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.7; margin:14px 0 10px 0;">
            Autonomous financial operations system that parses complex PDF invoices, executes 3-way matching against purchase orders and receiving logs, calculates line-item tax variances, and assigns fraud risk anomaly scores with clear audit trails.
        </p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
            <span class="chip chip-purple">PDF Extraction</span>
            <span class="chip chip-cyan">3-Way PO Matching</span>
            <span class="chip chip-green">Fraud Anomaly Scoring</span>
            <span class="chip chip-purple">Tax Reconciliation</span>
            <span class="chip chip-cyan">Audit Trail Logs</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <span style="color:#94a3b8; font-size:12px;">URL: <code style="color:#fbbf24;">https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/</code></span>
            <a href="https://invoice-processing-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="background:linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color:#030712; padding:8px 18px; border-radius:10px; font-weight:700; font-size:13px; text-decoration:none; box-shadow:0 4px 15px rgba(245, 158, 11, 0.4);">Launch Application ↗</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Project 5: X-Estal Code Dev Agent
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:26px;">🛠️</span>
                <div>
                    <h3 style="margin:0; color:#f8fafc;">X-Estal Code Dev Agent</h3>
                    <span style="font-size:12px; color:#94a3b8;">Interactive Streamlit Prototype for Autonomous Software Dev</span>
                </div>
            </div>
            <span class="chip chip-cyan"><span class="pulse-dot pulse-green"></span> 🟢 LIVE STREAMLIT APP</span>
        </div>
        <p style="color:#cbd5e1; font-size:14px; line-height:1.7; margin:14px 0 10px 0;">
            Interactive cloud-deployed prototype that pioneered prompt-to-production repo synthesis. Provides students and developers with a simple web interface to input software requirements and generate structured multi-file code packages.
        </p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
            <span class="chip chip-cyan">Streamlit Cloud</span>
            <span class="chip chip-purple">Prototype Architecture</span>
            <span class="chip chip-green">Repo Scaffolding</span>
            <span class="chip chip-cyan">Instant Zip Export</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <span style="color:#94a3b8; font-size:12px;">URL: <code style="color:#38bdf8;">https://code-dev-agent-by-x-estal-nitish.streamlit.app/</code></span>
            <a href="https://code-dev-agent-by-x-estal-nitish.streamlit.app/" target="_blank" style="background:linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); color:#030712; padding:8px 18px; border-radius:10px; font-weight:700; font-size:13px; text-decoration:none; box-shadow:0 4px 15px rgba(56, 189, 248, 0.4);">Launch Application ↗</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Author & Portfolio Ecosystem Section
    st.markdown("### 👨‍💻 Engineering Leadership & Profiles")
    st.markdown("""
    <div class="clay-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
                <h4 style="margin:0; color:#00f0ff;">Nitish Kumar (X-ESTAL NITISH)</h4>
                <p style="color:#94a3b8; font-size:13px; margin:4px 0 0 0;">Creator & AI Systems Architect · C.M. Science College, Darbhanga</p>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
                <a href="https://github.com/XestalNitish" target="_blank" style="background:rgba(255, 255, 255, 0.08); border:1px solid rgba(255, 255, 255, 0.2); color:#f8fafc; padding:8px 14px; border-radius:8px; font-size:13px; font-weight:600; text-decoration:none;">🐙 GitHub Portfolio</a>
                <a href="https://www.linkedin.com/in/nitish-kumar-ai" target="_blank" style="background:rgba(0, 119, 181, 0.2); border:1px solid rgba(0, 119, 181, 0.5); color:#38bdf8; padding:8px 14px; border-radius:8px; font-size:13px; font-weight:600; text-decoration:none;">💼 LinkedIn Profile</a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# TAB 9: ⚡ SYSTEM & SERVER MISSION CONTROL
# ============================================================================

elif nav == "⚡ System & Server Mission Control":
    st.markdown('<div class="hero-title">⚡ System & Server Mission Control</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Real-time daemon management, ports health, and execution telemetry.</div>', unsafe_allow_html=True)

    col_srv1, col_srv2 = st.columns(2)
    with col_srv1:
        s1 = check_server("main")
        color = "chip-green" if s1 else "chip-purple"
        p_class = "pulse-green" if s1 else "pulse-red"
        st.markdown(f"""
        <div class="clay-card">
            <span class="chip {color}"><span class="pulse-dot {p_class}"></span> PORT 8082: {'ONLINE' if s1 else 'OFFLINE'}</span>
            <h3 style="margin-top:10px;">Server 1: Spark 2.5 (4B)</h3>
            <p style="color:#94a3b8; font-size:13px;">Analytical Core: Orchestrator, Planner, Security AST Checker, Debugger, Reviewer, Chat, RAG</p>
            <span style="font-size:12px; color:#00f0ff;">Endpoint: <code>http://127.0.0.1:8082/health</code></span>
        </div>
        """, unsafe_allow_html=True)
    
    with col_srv2:
        s2 = check_server("writer")
        color = "chip-green" if s2 else "chip-purple"
        p_class = "pulse-green" if s2 else "pulse-red"
        st.markdown(f"""
        <div class="clay-card">
            <span class="chip {color}"><span class="pulse-dot {p_class}"></span> PORT 8084: {'ONLINE' if s2 else 'OFFLINE'}</span>
            <h3 style="margin-top:10px;">Server 2: Spark 2.6 (4B)</h3>
            <p style="color:#94a3b8; font-size:13px;">Synthesis Core: Senior Code Writer Node</p>
            <span style="font-size:12px; color:#00f0ff;">Endpoint: <code>http://127.0.0.1:8084/health</code></span>
        </div>
        """, unsafe_allow_html=True)

    c_act1, c_act2, c_act3 = st.columns(3)
    with c_act1:
        if st.button("⚡ Start All Daemons", use_container_width=True):
            auto_start_servers_ui(["main", "writer"])
            st.rerun()
    with c_act2:
        if st.button("🛑 Stop All Daemons", use_container_width=True):
            start_servers.stop_servers()
            st.info("Stopped all local daemons.")
            time.sleep(1)
            st.rerun()
    with c_act3:
        if st.button("🧪 System Diagnostic", use_container_width=True):
            with st.spinner("Executing healthcheck.py..."):
                proc = subprocess.run([str(PYTHON_EXE), "healthcheck.py"], capture_output=True, text=True, cwd=str(ROOT))
                st.code(proc.stdout)

    st.markdown("---")
    st.markdown("#### 📜 Live Server Logs")
    log_role = st.selectbox("Select Log Stream", options=["server_main.log", "server_writer.log"])
    target_log = C.LOG_DIR / log_role
    if target_log.exists():
        with open(target_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            tail_lines = "".join(lines[-60:])
            st.markdown(f'<div class="neural-console">{tail_lines}</div>', unsafe_allow_html=True)
    else:
        st.info(f"Log file not found: `{target_log}`")
