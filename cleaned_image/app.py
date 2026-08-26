import importlib.util

import streamlit as st

PdfReader = None
if importlib.util.find_spec("pypdf") is not None:
    from pypdf import PdfReader  # type: ignore[import-not-found]

fitz = None
if importlib.util.find_spec("fitz") is not None:
    import fitz  # type: ignore[import-not-found]

from pipeline import process_quotation_text
from db import fetch_all_items_df

st.set_page_config(page_title="AIC Quotation Extraction & Analytics Agent", layout="wide")
st.title("🧪 Chemical Quotation Extraction & Multi-Agent Analytics")

st.sidebar.header("Document Ingestion")
uploaded_pdf = st.sidebar.file_uploader("Upload AIC Quotation PDF", type=["pdf"])

if uploaded_pdf is not None:
    raw_text = ""

    if PdfReader is not None:
        pdf_reader = PdfReader(uploaded_pdf)
        for page in pdf_reader.pages:
            raw_text += page.extract_text() or ""
    elif fitz is not None:
        pdf_bytes = uploaded_pdf.getvalue()
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_no in range(pdf_document.page_count):
            page = pdf_document[page_no]
            raw_text += page.get_text() or ""
        pdf_document.close()
    else:
        raise RuntimeError("No PDF extraction backend is available in this environment")

    if st.sidebar.button("Run Multi-Agent Extraction"):
        with st.spinner("Processing document through extraction & categorization agents..."):
            extracted_data = process_quotation_text(raw_text)
            st.success("Extraction and Categorization completed successfully!")

st.subheader("📊 Extracted Line Items Database")
df = fetch_all_items_df()

if not df.empty:
    st.dataframe(df, use_container_width=True)

    st.subheader("💬 Expense Analytics Assistant")

    selected_category = st.selectbox(
        "Filter total expenditure by Category:",
        options=["All"] + list(df["category"].unique()),
    )

    if selected_category != "All":
        filtered_df = df[df["category"] == selected_category]
        total_exp = filtered_df["final_value"].sum()
        st.metric(
            label=f"Total Expenses for '{selected_category}'",
            value=f"₹ {total_exp:,.2f}",
        )
        st.dataframe(filtered_df, use_container_width=True)
    else:
        total_exp = df["final_value"].sum()
        st.metric(
            label="Grand Total Expenses (All Quotations)",
            value=f"₹ {total_exp:,.2f}",
        )
else:
    st.info("No quotation items stored in database. Upload a PDF and run extraction.")
