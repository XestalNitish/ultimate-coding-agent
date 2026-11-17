"""Pydantic models for Todo and Notes data structures."""

from pydantic import BaseModel, Field


class TodoItem(BaseModel):
    id: int
    title: str = Field(..., min_length=1, max_length=200)
    completed: bool = False


class TodoList(BaseModel):
    items: list[TodoItem]


class NotesItem(BaseModel):
    id: int
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class NotesList(BaseModel):
    items: list[NotesItem]