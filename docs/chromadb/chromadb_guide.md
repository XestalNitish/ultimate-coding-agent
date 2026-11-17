# ChromaDB Vector Database Reference

## Client Initialization and Collections
Chroma provides persistent vector storage and metadata filtering for semantic retrieval.

```python
import chromadb
from chromadb.config import Settings

# Persistent local client
client = chromadb.PersistentClient(path="./vectordb_chroma")

# Get or create collection
collection = client.get_or_create_collection(
    name="enterprise_docs",
    metadata={"hnsw:space": "cosine"}
)
```

## Adding Documents & Embeddings
Add text passages with rich metadata for multi-tenant and library filtering.

```python
collection.add(
    ids=["doc_1", "doc_2"],
    documents=[
        "FastAPI provides async path functions with high performance.",
        "Streamlit session_state preserves values across reruns."
    ],
    metadatas=[
        {"library": "fastapi", "version": "0.115", "type": "backend"},
        {"library": "streamlit", "version": "1.35", "type": "frontend"}
    ]
)
```

## Querying with Metadata Filters
Semantic search with filtering by library or workspace.

```python
results = collection.query(
    query_texts=["how to store session data in streamlit"],
    n_results=3,
    where={"library": "streamlit"}
)

for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f"[{meta['library']}] {doc[:100]}...")
```
