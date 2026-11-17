import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import chromadb
from datetime import datetime
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CleanedData(BaseModel):
    id: int = Field(primary_key=True)
    raw_text: str
    cleaned_text: str
    metadata: dict = {}

Base = declarative_base()

class AsyncDB:
    def __init__(self, db_path: str = "leviathan.db"):
        self.engine = create_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.chroma = chromadb.PersistentClient(path="chroma_leviathan")
        self.create_tables()

    async def create_tables(self):
        async with self.session_factory() as session:
            Base.metadata.create_all(self.engine)
        logger.info("SQLite and ChromaDB tables initialized.")

    async def save_data(self, data: CleanedData):
        async with self.session_factory() as session:
            session.add(data)
            await session.commit()
        logger.info(f"Saved record {data.id} to SQLite.")

    async def query_data(self, query: str, limit: int = 10) -> List[CleanedData]:
        async with self.session_factory() as session:
            result = await session.execute(
                __import__('sqlalchemy').select(CleanedData).where(CleanedData.raw_text.ilike(f"%{query}%"))
            )
            return list(result.all())

    async def ingest_chroma(self, text: str, metadata: dict = None):
        self.chroma.add(
            ids=[str(hash(text))],
            documents=[text],
            metadatas=metadata or {},
            embeddings=None,
            n_results=1
        )
        logger.info(f"Ingested text into ChromaDB: {text[:50]}...")