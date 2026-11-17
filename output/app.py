import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Project Leviathan", layout="wide")

def upload_files():
    csv_file = st.file_uploader("Upload CSV", type=["csv"])
    pdf_file = st.file_uploader("Upload PDF", type=["pdf"])
    return csv_file, pdf_file

def call_api(csv_file, pdf_file):
    try:
        with open(csv_file, "rb") as f:
            csv_data = f.read()
        with open(pdf_file, "rb") as f:
            pdf_data = f.read()
        payload = {
            "csv_file": (csv_file, csv_data),
            "pdf_file": (pdf_file, pdf_data)
        }
        response = requests.post("http://localhost:8000/workflow", files=payload, timeout=120)
        return response.json()
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return {"error": str(e)}

def render_chart(data):
    if not data or len(data) == 0:
        st.info("No data available for chart.")
        return
    df = pd.DataFrame(data)
    st.plotly_chart(go.DataFrame(df), use_container_width=True)

def run_ui():
    uploaded = upload_files()
    if uploaded[0] and uploaded[1]:
        result = call_api(uploaded[0], uploaded[1])
        if "error" not in result:
            st.success("Pipeline executed.")
            st.subheader("Execution Logs")
            st.write(result.get("logs", []))
            st.subheader("Data Analysis")
            render_chart(result.get("data", []))
        else:
            st.error(f"Execution failed: {result['error']}")
    else:
        st.info("Please upload a CSV and PDF file to proceed.")

if __name__ == "__main__":
    run_ui()