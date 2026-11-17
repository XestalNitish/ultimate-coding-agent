from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import sqlite3
from contextlib import contextmanager
import crud
import database
import schemas

app = FastAPI(
    title="Todo and Notes API",
    version="1.0.0",
    description="Modular FastAPI service for Todo and Notes resources backed by SQLite."
)


@app.post("/todos", response_model=schemas.TodoItem, status_code=status.HTTP_201_CREATED)
def create_todo_endpoint(title: str):
    if not title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty")
    return crud.create_todo(title)


@app.get("/todos", response_model=list[schemas.TodoItem])
def list_todos_endpoint():
    return crud.list_todos()


@app.post("/notes", response_model=schemas.NotesItem, status_code=status.HTTP_201_CREATED)
def create_notes_endpoint(title: str, content: str):
    if not title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty")
    return crud.create_notes(title, content)


@app.get("/notes", response_model=list[schemas.NotesItem])
def list_notes_endpoint():
    return crud.list_notes()


def init_db():
    database.init_db()


def test_create_and_list_todos():
    created = crud.create_todo("Test todo item")
    listed = crud.list_todos()
    assert created.id > 0
    assert created.title == "Test todo item"
    assert created.completed is False
    assert any(item.id == created.id for item in listed)


def test_create_and_list_notes():
    created = crud.create_notes("Test note title", "Test note content")
    listed = crud.list_notes()
    assert created.id > 0
    assert created.title == "Test note title"
    assert created.content == "Test note content"
    assert any(item.id == created.id for item in listed)


if __name__ == "__main__":
    init_db()
    test_create_and_list_todos()
    test_create_and_list_notes()