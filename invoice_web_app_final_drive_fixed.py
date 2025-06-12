
import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import base64
import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

st.set_page_config(page_title="Taz-IT Invoice Generator", layout="centered")
st.title("📄 Taz-IT Invoice Generator")

# Invoice Meta
st.subheader("Invoice Details")
invoice_number = st.text_input("Invoice Number", value="1001")
invoice_date = st.date_input("Invoice Date", value=datetime.today())

# Client Info
st.subheader("Client Information")
client_name = st.text_input("Client Name", value="Bon Vibe")
client_address = st.text_input("Client Address", value="Kerkstraat 4, Aruba")
client_phone = st.text_input("Client Phone", value="297 746 3522")

# Line Items
st.subheader("Line Items")
item_df = st.data_editor(
    pd.DataFrame(columns=["Description", "Units", "Qty", "Rate (AWG)"]),
    num_rows="dynamic",
    use_container_width=True
)

FOLDER_ID = "1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"

def generate_pdf_bytes(invoice_number, invoice_date, client_name, client_address, client_phone, df):
    pdf = FPDF()
    pdf.add_page()

    # Logo
    logo_path = "tazit_logo_pdf.png"
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)
        pdf.set_y(12)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "INVOICE", ln=True, align="R")

    pdf.set_font("Arial", "", 10)
    pdf.cell(100, 8, "Taz-IT Solutions", ln=True)
    pdf.cell(100, 5, "Pos Chikito 99B", ln=True)
    pdf.cell(100, 5, "Oranjestad, Aruba", ln=True)
    pdf.cell(100, 5, "(+297) 699-7692 | jcroes@tazitsolution.com", ln=True)

    pdf.ln(5)
    pdf.cell(100, 6, f"Bill To: {client_name}", ln=False)
    pdf.cell(100, 6, f"Invoice #: {invoice_number}", ln=True)
    pdf.cell(100, 6, f"{client_address}", ln=False)
    pdf.cell(100, 6, f"Date: {invoice_date.strftime('%d-%b-%Y')}", ln=True)
    pdf.cell(100, 6, f"{client_phone}", ln=True)

    pdf.ln(5)
    pdf.set_fill_color(192, 0, 0)
    pdf.set_text_color(255)
    pdf.set_font("Arial", "B", 10)
    headers = ["Description", "Units", "Qty", "Rate", "Total"]
    col_widths = [60, 25, 20, 30, 30]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align='C', fill=True)
    pdf.ln()

    pdf.set_text_color(0)
    pdf.set_font("Arial", "", 10)
    subtotal = 0
    for _, row in df.iterrows():
        desc = str(row.get("Description", "")).strip()
        if not desc:
            continue
        qty = pd.to_numeric(row.get("Qty", 0), errors="coerce") or 0
        rate = pd.to_numeric(row.get("Rate (AWG)", 0), errors="coerce") or 0
        total = qty * rate
        subtotal += total
        values = [desc, row.get("Units", ""), qty, rate, total]
        for i, val in enumerate(values):
            pdf.cell(col_widths[i], 8, str(val), border=1)
        pdf.ln()

    tax = subtotal * 0.12
    grand_total = subtotal + tax
    pdf.ln(3)
    for label, value in [("Subtotal", subtotal), ("Tax (12%)", tax), ("Total", grand_total)]:
        pdf.cell(135, 8, label, align="R")
        pdf.cell(30, 8, f"{value:.2f} AWG", border=1, ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Thank you for your business!", ln=True)
    pdf.cell(0, 5, "Payment due within 14 days.", ln=True)

    pdf.ln(8)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, "Bank Payment Info:", ln=True)
    pdf.cell(0, 5, "Bank: Aruba Bank", ln=True)
    pdf.cell(0, 5, "Account Name: Joshua Croes", ln=True)
    pdf.cell(0, 5, "Account Number: 3066850190", ln=True)
    pdf.cell(0, 5, "SWIFT/BIC: ARUBAWAW", ln=True)
    pdf.cell(0, 5, "Currency: AWG", ln=True)

    return pdf.output(dest="S").encode("latin-1")

def upload_to_drive(filename, file_bytes):
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/drive"])
    drive_service = build("drive", "v3", credentials=creds)

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype="application/pdf")
    file_metadata = {
        "name": filename,
        "parents": [FOLDER_ID]
    }
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file.get("id")

if st.button("Generate & Upload Invoice"):
    valid_df = item_df.dropna(subset=["Description"])
    if valid_df.empty:
        st.warning("Please enter at least one line item.")
    else:
        filename = f"Invoice_{invoice_number}.pdf"
        pdf_bytes = generate_pdf_bytes(invoice_number, invoice_date, client_name, client_address, client_phone, valid_df)
        file_id = upload_to_drive(filename, pdf_bytes)
        st.success(f"✅ Invoice uploaded to Google Drive (File ID: {file_id})")

        st.subheader("🔍 PDF Preview")
        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
        st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px"></iframe>', unsafe_allow_html=True)
        st.download_button("📄 Download PDF", data=pdf_bytes, file_name=filename, mime="application/pdf")
