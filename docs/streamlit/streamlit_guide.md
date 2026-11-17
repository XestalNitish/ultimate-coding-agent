# Streamlit Guide for AI Applications & Chatbots

## Application Setup and Page Config
Configure modern dashboard layouts, dark themes, and titles.

```python
import streamlit as st

st.set_page_config(
    page_title="AI Agentic Workspace",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)
```

## Session State and Chat History
Maintain persistent state across Streamlit execution cycles.

```python
import streamlit as st

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": "Namaste! Main aapka AI assistant hoon. Kaise madad karun?"}
    ]

# Render conversation history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
```

## Chat Input and Streaming Responses
Live token streaming using `st.chat_input` and `st.write_stream`.

```python
import streamlit as st

if prompt := st.chat_input("Apna sawal yahan likhein..."):
    # Append and display user message
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate assistant answer
    with st.chat_message("assistant"):
        with st.spinner("AI soch raha hai..."):
            response_placeholder = st.empty()
            full_response = ""
            # Stream or generate
            for token in ["Analyzing ", "requirements... ", "Complete."]:
                full_response += token
                response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)
    st.session_state.chat_history.append({"role": "assistant", "content": full_response})
```

## Sidebar Controls and Parameters
Sidebar controls for model temperature, workspace selection, and API keys.

```python
with st.sidebar:
    st.header("⚙️ Agent Settings")
    model_choice = st.selectbox("LLM Model", ["Spark-X2.5-4B", "Qwen2.5-Coder-3B"])
    temperature = st.slider("Creativity (Temperature)", min_value=0.0, max_value=1.0, value=0.2, step=0.05)
    enable_rag = st.toggle("Enable RAG Context", value=True)
    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
```

## Glassmorphism UI & Custom CSS
Custom styling for professional enterprise appearance.

```python
st.markdown("""
<style>
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)
```
