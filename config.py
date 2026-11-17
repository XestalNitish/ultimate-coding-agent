"""Central config - saari settings yahin se tune karo."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.resolve()
load_dotenv(ROOT / ".env")

# ---------------- LangSmith Observability ----------------
# Clean up conflicting agent addressing variables to prevent EnvAddressError
for conflicting_var in ("LANGSMITH_AGENT_ID", "LANGSMITH_AGENT_ENVIRONMENT", "LANGSMITH_AGENT_NAME"):
    os.environ.pop(conflicting_var, None)

LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT", "ultimate-coding-agent")

if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGSMITH_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT
    os.environ["LANGSMITH_PROJECT"] = LANGCHAIN_PROJECT
    os.environ["LANGSMITH_TRACING"] = "true"
    print(f"[LangSmith] Tracing enabled for project: {LANGCHAIN_PROJECT}")
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"

MODELS_DIR = ROOT / "models"
DOCS_DIR = ROOT / "docs"
DB_DIR = ROOT / "vectordb"
WORK_DIR = ROOT / "workspace"
LOG_DIR = ROOT / "logs"

LLAMA_SERVER = os.environ.get("LLAMA_SERVER", "llama-server")

THREADS = int(os.environ.get("LLM_THREADS", max(1, (os.cpu_count() or 4) // 2)))

EXTRA_ARGS: list = ["--device", "none", "--no-op-offload", "--reasoning", "off", "--reasoning-format", "none", "--no-reasoning-preserve"]


MODELS = {
    "main": dict(
        repo="XHToken/Spark-X2.5-4B-GGUF", file=None, quant="Q4_K_M", local_path=None,
        port=int(os.environ.get("XESTAL_PORT", 8082)), ctx=16384, ngl=0, max_tokens=4096, no_think=True,
    ),
    "summarizer": dict(same_as="main", max_tokens=2048),
    "coder": dict(same_as="main", max_tokens=8192, no_think=True),
    "writer": dict(
        repo="XHToken/Spark-X2.6-4B-GGUF", file=None, quant="Q4_K_M", local_path=None,
        port=int(os.environ.get("XESTAL_PORT2", os.environ.get("CODE_DEV_WRITER_PORT", 8084))),
        ctx=16384, ngl=0, max_tokens=12288, no_think=True,
    ),
}


def real_role(role: str) -> str:
    """summarizer -> main (same_as follow karo)."""
    return MODELS[role].get("same_as", role)


def model_path(role: str) -> Path:
    cfg = MODELS[real_role(role)]
    if cfg.get("local_path"):
        return Path(cfg["local_path"])
    if cfg.get("file"):
        return MODELS_DIR / cfg["file"]
    d = MODELS_DIR / cfg["repo"].replace("/", "__")
    found = sorted(p for p in d.glob("*.gguf") if "mmproj" not in p.name.lower())
    pref = [p for p in found if cfg.get("quant", "").lower() in p.name.lower()]
    return (pref or found or [d / "NOT_DOWNLOADED.gguf"])[0]


# ---------------- RAG ----------------
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RAG_TOP_K = 3
CHUNK_CHARS = 1200

# ---------------- Pipeline ----------------
USE_RESEARCHER = True       # False = skip slow web search and start coding immediately
USE_DEEP_RESEARCH = True   # True = invoke full research_web_agent (deep report + audit)
MAX_RETRIES = 3              # debugger retries (also used as max_iterations for coder agent)
MAX_PLANNER_RESTARTS = 0     # 0 = never wipe files and restart planner from scratch
MAX_PLANNER_RAG_CALLS = 1    # fast docs (1 call max)
TEST_TIMEOUT = 30            # seconds
SUMMARY_TOKENS = 350

# Ye packages missing ho to code ko galat nahi maante (sirf note lagta hai)
KNOWN_PACKAGES = {
    "streamlit", "fastapi", "uvicorn", "pydantic", "requests", "httpx", "numpy",
    "pandas", "flask", "sqlalchemy", "matplotlib", "scipy", "pytest", "langgraph",
}
