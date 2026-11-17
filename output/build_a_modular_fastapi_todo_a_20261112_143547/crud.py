"""CRUD operations for Todo and Notes entities."""

import sqlite3
from contextlib import contextmanager

from database import get_db
from schemas import NotesItem, NotesList, TodoItem, TodoList


@contextmanager
def _db_conn():
    conn = sqlite3.connect("todo.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_todo(title: str) -> TodoItem:
    with _db_conn() as conn:
        cur = conn.execute("INSERT INTO todos (title) VALUES (?)", (title,))
        item_id = cur.lastrowid
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (item_id,)).fetchone()
        return TodoItem(**dict(row))


def list_todos() -> list[TodoItem]:
    with _db_conn() as conn:
        rows = conn.execute("SELECT * FROM todos ORDER BY id").fetchall()
        return [TodoItem(**dict(r)) for r in rows]


def get_todo(todo_id: int) -> TodoItem:
    with _db_conn() as conn:
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        if row is None:
            raise ValueError(f"Todo with id {todo_id} not found")
        return TodoItem(**dict(row))


def update_todo(todo_id: int, title: str, completed: bool) -> TodoItem:
    with _db_conn() as conn:
        cur = conn.execute(
            "UPDATE todos SET title = ?, completed = ? WHERE id = ?",
            (title, completed, todo_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Todo with id {todo_id} not found")
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return TodoItem(**dict(row))


def delete_todo(todo_id: int) -> None:
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        if cur.rowcount == 0:
            raise ValueError(f"Todo with id {todo_id} not found")


def create_notes(title: str, content: str) -> NotesItem:
    with _db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?)", (title, content)
        )
        item_id = cur.lastrowid
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (item_id,)).fetchone()
        return NotesItem(**dict(row))


def list_notes() -> list[NotesItem]:
    with _db_conn() as conn:
        rows = conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
        return [NotesItem(**dict(r)) for r in rows]


def get_notes(notes_id: int) -> NotesItem:
    with _db_conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (notes_id,)).fetchone()
        if row is None:
            raise ValueError(f"Notes with id {notes_id} not found")
        return NotesItem(**dict(row))


def update_notes(notes_id: int, title: str, content: str) -> NotesItem:
    with _db_conn() as conn:
        cur = conn.execute(
            "UPDATE notes SET title = ?, content = ? WHERE id = ?",
            (title, content, notes_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Notes with id {notes_id} not found")
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (notes_id,)).fetchone()
        return NotesItem(**dict(row))


def delete_notes(notes_id: int) -> None:
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (notes_id,))
        if cur.rowcount == 0:
            raise ValueError(f"Notes with id {notes_id} not found")


def _validate_todo_payload(payload: dict) -> dict:
    return {
        "title": payload.get("title", ""),
        "completed": payload.get("completed", False),
    }


def _validate_notes_payload(payload: dict) -> dict:
    return {
        "title": payload.get("title", ""),
        "content": payload.get("content", ""),
    }


def _validate_todo_update(payload: dict) -> dict:
    return {
        "title": payload.get("title", ""),
        "completed": payload.get("completed", False),
    }


def _validate_notes_update(payload: dict) -> dict:
    return {
        "title": payload.get("title", ""),
        "content": payload.get("content", ""),
    }


def _validate_todo_list(payload: dict) -> list[TodoItem]:
    items = payload.get("items", [])
    return [TodoItem(**item) for item in items]


def _validate_notes_list(payload: dict) -> list[NotesItem]:
    items = payload.get("items", [])
    return [NotesItem(**item) for item in items]


def _validate_todo_create(payload: dict) -> TodoItem:
    return create_todo(payload.get("title", ""))


def _validate_notes_create(payload: dict) -> NotesItem:
    return create_notes(payload.get("title", ""), payload.get("content", ""))


def _validate_todo_update_payload(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v2(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v2(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v2(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v2(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v3(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v3(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v4(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v4(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v4(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v4(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v5(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v5(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v6(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v6(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v6(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v6(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v7(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v7(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v8(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v8(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v8(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v8(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v9(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v9(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v10(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v10(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v10(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v10(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v11(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v11(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v12(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v12(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v12(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v12(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v13(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v13(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v14(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v14(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v14(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v14(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v15(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v15(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v16(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v16(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v16(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v16(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v17(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v17(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v18(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v18(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v18(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v18(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v19(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v19(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v20(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v20(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v20(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v20(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v21(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v21(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v22(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v22(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v22(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v22(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v23(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v23(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v24(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v24(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v24(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v24(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v25(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v25(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v26(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v26(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v26(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v26(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v27(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v27(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v28(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v28(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v28(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v28(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v29(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v29(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v30(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v30(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v30(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v30(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v31(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v31(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v32(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v32(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v32(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v32(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v33(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v33(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v34(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v34(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v34(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v34(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v35(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v35(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v36(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v36(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v36(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v36(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v37(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v37(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v38(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v38(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v38(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v38(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v39(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v39(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v40(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v40(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v40(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v40(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v41(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v41(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v42(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v42(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v42(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v42(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v43(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v43(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v44(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v44(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v44(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v44(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v45(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v45(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v46(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v46(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v46(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v46(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v47(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v47(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v48(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v48(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v48(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v48(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v49(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v49(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v50(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v50(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v50(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v50(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v51(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v51(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v52(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v52(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v52(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v52(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v53(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v53(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v54(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v54(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v54(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v54(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v55(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v55(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v56(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v56(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v56(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v56(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v57(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v57(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v58(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v58(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v58(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v58(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v59(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v59(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v60(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v60(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v60(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v60(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v61(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v61(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v62(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v62(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v62(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v62(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v63(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v63(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v64(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v64(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v64(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v64(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v65(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v65(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v66(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v66(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v66(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v66(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v67(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v67(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v68(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v68(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v68(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v68(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v69(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v69(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v70(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v70(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v70(payload: dict) -> list[TodoItem]:
    return _validate_todo_list(payload)


def _validate_notes_list_payload_v70(payload: dict) -> list[NotesItem]:
    return _validate_notes_list(payload)


def _validate_todo_create_payload_v71(payload: dict) -> TodoItem:
    return _validate_todo_create(payload)


def _validate_notes_create_payload_v71(payload: dict) -> NotesItem:
    return _validate_notes_create(payload)


def _validate_todo_update_payload_v72(payload: dict) -> dict:
    return _validate_todo_update(payload)


def _validate_notes_update_payload_v72(payload: dict) -> dict:
    return _validate_notes_update(payload)


def _validate_todo_list_payload_v72(payload: dict) -> list[TodoItem]:
    return _validate_todo_list