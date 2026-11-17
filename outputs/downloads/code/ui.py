import streamlit as st
from typing import Any, Dict, List, Optional

def run_ui() -> None:
    st.set_page_config(page_title="Todo Dashboard", layout="wide")
    
    # KPI Metrics
    try:
        storage = storage
        stats = storage.get_stats()
        st.title("📋 Todo Dashboard")
        st.subheader("KPI Metrics")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Tasks", stats.get("total", 0))
        col2.metric("Pending", stats.get("pending", 0))
        col3.metric("Completed", stats.get("completed", 0))
    except Exception as e:
        st.error(f"Failed to load stats: {e}")
        return

    # Sidebar Form
    with st.sidebar:
        st.header("Add New Todo")
        form = st.form("new_todo_form", clear_on_submit=True)
        title = form.text_input("Task Title", placeholder="Enter task title")
        priority = form.selectbox("Priority", ["Low", "Medium", "High"])
        tag = form.text_input("Tag", placeholder="General")
        due_date = form.date_input("Due Date")
        
        if form.submit():
            if title.strip():
                result = storage.add_todo(
                    title=title.strip(),
                    priority=priority,
                    tag=tag.strip() or "General",
                    due_date=due_date
                )
                st.success(f"Todo added successfully! ID: {result.get('id')}")
            else:
                st.warning("Task title cannot be empty.")

    # Main Feed & Filters
    st.subheader("Task Feed")
    tabs = st.tabs(["Pending Tasks", "Completed", "All"])
    
    for tab in tabs:
        with tab:
            if tab == "Pending Tasks":
                filtered = [t for t in storage.load_todos() if t.get("status") == "pending"]
            elif tab == "Completed":
                filtered = [t for t in storage.load_todos() if t.get("status") == "completed"]
            else:
                filtered = storage.load_todos()
            
            if not filtered:
                st.info("No tasks found in this category.")
                continue
            
            for item in filtered:
                st.container(border=True)
                st.markdown(f"**ID:** {item.get('id')} | **Title:** {item.get('title')}")
                if item.get("description"):
                    st.markdown(f"**Description:** {item.get('description')}")
                st.markdown(f"**Status:** {item.get('status')} | **Priority:** {item.get('priority')} | **Tag:** {item.get('tag')}")
                if item.get("due_date"):
                    st.markdown(f"**Due Date:** {item.get('due_date')}")
                
                st.button("Mark Done", key=f"done_{item.get('id')}", use_container_width=True)
                st.button("Delete", key=f"del_{item.get('id')}", use_container_width=True)