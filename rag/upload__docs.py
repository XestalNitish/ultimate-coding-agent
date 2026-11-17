"""
upload__docs.py - Document Ingestion & RAG Indexing Pipeline
============================================================
Loads documents (PDF, DOCX, Web Link, YouTube, Video), chunks them semantically,
and stores them into ChromaDB and the fast RAG vector store tagged by library.

Usage:
    python rag/upload__docs.py --file path/to/doc.pdf --library streamlit
    python rag/upload__docs.py --link https://example.com --library python
    python rag/upload__docs.py --text "some documentation text" --library html
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from langgraph.graph import END, StateGraph

# Safe imports resolving within rag package or root
try:
    from rag.tools import docx_reader, pdf_reader, video_reader, web_reader, youtube
    from rag.database import chroma_store, smart_chunk_document
except ImportError:
    from tools import docx_reader, pdf_reader, video_reader, web_reader, youtube
    from database import chroma_store, smart_chunk_document

import config as C
import rag


class UploadState(TypedDict, total=False):
    file_path: str
    file_type: Literal["docs", "pdf", "link", "youtube_link", "local_video", "text"]
    workspace_id: str
    library: str
    source: Optional[str]
    loader: Any
    structured_chunks: List[Dict[str, Any]]
    status: str
    db_store: Any
    collection_name: str


LOADERS = {
    "docs": docx_reader,
    "pdf": pdf_reader,
    "link": web_reader,
    "local_video": video_reader,
    "youtube_link": youtube,
}


def upload_documents(state: UploadState):
    print(f"--- STEP 1: LOADING DOCUMENT ({state.get('file_type')}) ---")
    ftype = state.get("file_type", "pdf")
    fpath = state.get("file_path", "")
    try:
        if ftype == "text":
            return {"loader": fpath, "status": "loaded"}
        tool = LOADERS.get(ftype)
        if tool is None:
            raise ValueError(f"Unsupported file type: {ftype}")
        loader = tool.invoke(fpath)
        return {"loader": loader, "status": "loaded"}
    except Exception as e:
        print(f"[ERROR] Loading failed: {e}")
        return {"status": f"error: loading failed: {e}"}


def chunking(state: UploadState):
    print("--- STEP 2: CHUNKING DOCUMENT WITH METADATA ---")
    source = state.get("source") or state.get("file_path", "raw_text")
    library = state.get("library") or state.get("workspace_id", "general")
    try:
        data = smart_chunk_document.invoke({
            "text_content": str(state.get("loader", "")),
            "source_name": source,
            "workspace_id": library,
        })
        return {"structured_chunks": data, "source": source, "status": "chunked"}
    except Exception as e:
        print(f"[ERROR] Chunking failed: {e}")
        return {"status": f"error: chunking failed: {e}"}


def store_chunks(state: UploadState):
    print("--- STEP 3: STORING IN RAG VECTOR STORE & CHROMADB ---")
    library = (state.get("library") or state.get("workspace_id", "general")).lower()
    chunks = state.get("structured_chunks", [])
    if not chunks:
        return {"status": "error: no chunks to store"}

    try:
        # 1. Store in ChromaDB
        col_name = state.get("collection_name") or os.getenv("RAG_COLLECTION", "enterprise_docs")
        chroma_res = chroma_store.invoke({
            "structured_chunks": chunks,
            "workspace_id": library,
            "collection_name": col_name,
        })

        # 2. Also register into fast in-memory store (used by rag.search)
        store = rag.get_store(reload=False)
        rag_chunks = []
        texts = []
        for c in chunks:
            text = c.get("text", "")
            if not text.strip():
                continue
            meta = c.get("metadata", {})
            header = f"[{library} | {meta.get('source', 'doc')}]"
            chunk_text = f"{header}\n{text}" if not text.startswith("[") else text
            rag_chunks.append({
                "text": chunk_text,
                "library": library,
                "version": meta.get("version", ""),
                "source": meta.get("source", str(state.get("file_path"))),
                "page": meta.get("page", 1),
                "heading": meta.get("source", ""),
            })
            texts.append(chunk_text)

        if texts:
            vecs = rag.embed_docs(texts)
            store.add(rag_chunks, vecs)
            store.save()
            print(f"[SUCCESS] Indexed {len(rag_chunks)} chunks for library '{library}' into RAG store.")

        return {"db_store": chroma_res, "status": "done"}
    except Exception as e:
        print(f"[ERROR] Storing failed: {e}")
        return {"status": f"error: storing failed: {e}"}


def check(next_node):
    def router(state: UploadState):
        return END if str(state.get("status", "")).startswith("error") else next_node
    return router


graph = StateGraph(UploadState)
graph.add_node("load", upload_documents)
graph.add_node("chunk", chunking)
graph.add_node("store", store_chunks)
graph.set_entry_point("load")
graph.add_conditional_edges("load", check("chunk"))
graph.add_conditional_edges("chunk", check("store"))
graph.add_edge("store", END)
app = graph.compile()


def upload_file(path_or_url: str, library: str, file_type: Optional[str] = None) -> dict:
    """Helper to upload a file or link into RAG under a library name."""
    if not file_type:
        p = path_or_url.lower()
        if p.startswith(("http://", "https://")):
            file_type = "youtube_link" if ("youtube.com" in p or "youtu.be" in p) else "link"
        elif p.endswith(".pdf"):
            file_type = "pdf"
        elif p.endswith((".docx", ".doc")):
            file_type = "docs"
        elif p.endswith((".mp4", ".avi", ".mov", ".mkv")):
            file_type = "local_video"
        else:
            file_type = "docs"
    return app.invoke({
        "file_path": path_or_url,
        "file_type": file_type,
        "library": library.strip().lower(),
        "workspace_id": library.strip().lower(),
    })


def upload_directory(dir_path: str) -> int:
    """Batch-ingest all documents in docs/<library>/* using the LangGraph upload pipeline."""
    p = Path(dir_path)
    if not p.exists():
        print(f"Directory {dir_path} does not exist.")
        return 1
    files = [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in {".pdf", ".md", ".txt", ".docx", ".doc"}]
    if not files:
        print(f"No documents found in {dir_path}.")
        return 0
    print(f"Found {len(files)} files to upload via LangGraph upload pipeline...")
    success = 0
    for f in files:
        rel = f.relative_to(p)
        lib = rel.parts[0].split("@")[0].strip().lower() if len(rel.parts) > 1 else f.stem.lower()
        print(f"\n[UPLOAD] {f.name} -> library: '{lib}'")
        if f.suffix.lower() in {".md", ".txt"}:
            res = app.invoke({
                "file_path": str(f),
                "file_type": "text",
                "loader": f.read_text(encoding="utf-8", errors="replace"),
                "library": lib,
                "workspace_id": lib,
                "source": f.name,
            })
        else:
            res = upload_file(str(f), library=lib)
        if res.get("status") == "done":
            success += 1
    print(f"\nBatch upload complete: {success}/{len(files)} files indexed successfully.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Upload and ingest documents into RAG library index")
    ap.add_argument("--file", help="Path to PDF, DOCX, video file")
    ap.add_argument("--link", help="Web page or YouTube URL")
    ap.add_argument("--dir", help="Directory of docs (e.g. docs/) with library subfolders to batch-upload")
    ap.add_argument("--library", help="Target library (e.g. python, streamlit, langchain, langgraph, html)")
    ap.add_argument("--type", choices=["docs", "pdf", "link", "youtube_link", "local_video", "text"], help="Override file type")
    args = ap.parse_args()

    if args.dir:
        return upload_directory(args.dir)

    target = args.file or args.link
    if not target:
        print("Please provide --file, --link, or --dir.")
        return 1
    if not args.library:
        print("Please provide --library for the file/link upload.")
        return 1

    res = upload_file(target, library=args.library, file_type=args.type)
    print(f"Status: {res.get('status')}")
    return 0 if res.get("status") == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
