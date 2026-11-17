import streamlit as st
from models import TodoItem
from storage import storage, load_todos, save_todos, add_todo, update_status, delete_todo, get_stats

def run():
    st.set_page_config(page_title="Todo Dashboard", page_icon="📝", layout="wide")
    
    # Sidebar KPI Metrics & Form
    with st.sidebar:
        st.title("📊 Dashboard")
        st.caption("Task Manager Overview")
        
        stats = get_stats()
        st.metric("Total Tasks", stats.get("total", 0))
        st.metric("Pending", stats.get("pending", 0))
        st.metric("Completed", stats.get("completed", 0))
        
        with st.form("new_todo_form", clear_on_submit=True):
            title = st.text_input("Task Title", placeholder="Enter task title")
            priority = st.selectbox("Priority", ["Low", "Medium", "High"])
            tag = st.text_input("Tag", placeholder="General")
            due_date = st.date_input("Due Date")
            
            if st.form_submit_button("Add New Todo"):
                if title.strip():
                    new_todo = add_todo(title=title.strip(), priority=priority, tag=tag.strip() or "General", due_date=str(due_date) if due_date else None)
                    st.rerun()
                else:
                    st.warning("Title is required.")

    # Main Feed & Filters
    tabs = st.tabs(["Pending Tasks", "Completed", "All"])
    
    for tab in tabs:
        with tab:
            all_todos = load_todos()
            
            if tab == "Pending Tasks":
                filtered = [t for t in all_todos if t.get("status") == "pending"]
            elif tab == "Completed":
                filtered = [t for t in all_todos if t.get("status") == "completed"]
            else:
                filtered = all_todos
            
            if not filtered:
                st.info("No tasks found in this category.")
                continue
            
            with st.container(border=True):
                for item in filtered:
                    todo_id = item.get("id")
                    st.subheader(f"#{todo_id} - {item.get('title', 'Untitled')}")
                    
                    if item.get("description"):
                        st.write(f"**Description:** {item.get('description')}")
                    
                    if item.get("priority"):
                        st.write(f"**Priority:** {item.get('priority')}")
                    
                    if item.get("tag"):
                        st.write(f"**Tag:** {item.get('tag')}")
                    
                    if item.get("due_date"):
                        st.write(f"**Due Date:** {item.get('due_date')}")
                    
                    if item.get("status") == "completed":
                        st.caption("✅ Completed")
                    
                    # Action buttons with deterministic keys
                    if st.button("Mark Done", key=f"done_{todo_id}", use_container_width=True):
                        update_status(todo_id, "completed")
                        st.rerun()
                    
                    if st.button("Delete", key=f"del_{todo_id}", use_container_width=True):
                        delete_todo(todo_id)
                        st.rerun()

if __name__ == "__main__":
    run()