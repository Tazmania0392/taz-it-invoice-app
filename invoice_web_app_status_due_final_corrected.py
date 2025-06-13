
# streamlit_invoice_app_final.py

import streamlit as st
import pandas as pd
from fpdf import FPDF
from io import BytesIO
import datetime
import tempfile
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Constants
FOLDER_NAME = "Invoices"
LOGO_PATH = "logo.png"  # Ensure logo is deployed
BRANDING_MESSAGE = "Thank you for your business! Payment due within 14 days.\nFor any questions, contact us at support@tazitsolution.com"
COMPANY_INFO = "Taz IT Solution\nPos Chikito 99B, Aruba\n+297 6997692\njcroes@tazitsolution.com\nwww.tazitsolution.com"

# Streamlit UI
st.set_page_config(page_title="Taz IT Invoice Generator", layout="centered")
st.title("📄 Taz IT Invoice Generator")

# Input fields
invoice_number = st.text_input("Invoice Number")
invoice_date = st.date_input("Invoice Date", value=datetime.date.today())
client_name = st.text_input("Client Business Name")
client_address = st.text_area("Client Address")
client_phone = st.text_input("Client Phone Number")
due_date = st.date_input("Due Date")
tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=100.0, value=12.0)
reverse_tax = st.checkbox("Apply Reverse Tax")

uploaded_file = st.file_uploader("Upload Excel Line Items", type=["xlsx"])

status_option = st.selectbox("Invoice Status", ["Unpaid", "Paid"])

GOOGLE_SERVICE_ACCOUNT = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
SERVICE_ACCOUNT_FILE = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
SERVICE_ACCOUNT_FILE.write(GOOGLE_SERVICE_ACCOUNT.encode())
SERVICE_ACCOUNT_FILE.close()

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE.name,
    scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
)
drive_service = build("drive", "v3", credentials=creds)
sheet_service = build("sheets", "v4", credentials=creds)

def generate_pdf(buffer, rows, total, logo_path=None):
    pdf = FPDF()
    pdf.add_page()
    if logo_path and os.path.exists(logo_path):
        pdf.image(logo_path, x=150, y=10, w=40)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, "INVOICE", ln=True, align="C")

    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, COMPANY_INFO)
    pdf.ln(2)
    pdf.multi_cell(0, 8, f"Client: {client_name}\nAddress: {client_address}\nPhone: {client_phone}")
    pdf.ln(1)
    pdf.cell(0, 8, f"Invoice No: {invoice_number}    Date: {invoice_date}    Due: {due_date}", ln=True)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(50, 10, "Description", 1)
    pdf.cell(30, 10, "Qty", 1)
    pdf.cell(40, 10, "Rate (AWG)", 1)
    pdf.cell(40, 10, "Total (AWG)", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 12)
    for _, row in rows.iterrows():
        pdf.cell(50, 10, str(row["Description"]), 1)
        pdf.cell(30, 10, str(row["Qty"]), 1)
        pdf.cell(40, 10, str(row["Rate (AWG)"]), 1)
        pdf.cell(40, 10, str(row["Total (AWG)"]), 1)
        pdf.ln()

    pdf.set_font("Arial", "B", 12)
    pdf.cell(120, 10, "Subtotal", 1)
    pdf.cell(40, 10, f"{total:.2f}", 1)
    pdf.ln()

    tax_amount = 0 if reverse_tax else (tax_rate / 100) * total
    total_due = total if reverse_tax else total + tax_amount

    if not reverse_tax:
        pdf.cell(120, 10, f"Tax ({tax_rate}%)", 1)
        pdf.cell(40, 10, f"{tax_amount:.2f}", 1)
        pdf.ln()

    pdf.cell(120, 10, "Total Due", 1)
    pdf.cell(40, 10, f"{total_due:.2f}", 1)
    pdf.ln(10)

    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 8, BRANDING_MESSAGE)

    pdf.output(buffer)
    buffer.seek(0)
    return buffer, total_due

def create_folder_if_not_exists(folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    folders = drive_service.files().list(q=query, fields="files(id)").execute()
    if folders["files"]:
        return folders["files"][0]["id"]
    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    return folder["id"]

def upload_pdf_to_drive(buffer, filename, parent_folder):
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp.write(buffer.read())
    temp.seek(0)
    media = MediaFileUpload(temp.name, mimetype="application/pdf")
    file = drive_service.files().create(body={"name": filename, "parents": [parent_folder]}, media_body=media, fields="id").execute()
    return file["id"]

def log_to_sheets(spreadsheet_id, values):
    sheet_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Invoices!A2",
        valueInputOption="USER_ENTERED",
        body={"values": [values]}
    ).execute()

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df["Total (AWG)"] = df["Qty"] * df["Rate (AWG)"]
    total = df["Total (AWG)"].sum()

    with BytesIO() as buffer:
        pdf_buffer, total_due = generate_pdf(buffer, df, total, LOGO_PATH)
        invoice_filename = f"{invoice_number}_{client_name.replace(' ', '_')}.pdf"

        base_folder = create_folder_if_not_exists(FOLDER_NAME)
        client_folder = create_folder_if_not_exists(client_name, parent_id=base_folder)
        file_id = upload_pdf_to_drive(pdf_buffer, invoice_filename, parent_folder=client_folder)

        overdue = datetime.date.today() > due_date
        spreadsheet_id = "your-google-sheet-id"
        log_to_sheets(spreadsheet_id, [
            str(invoice_number), str(invoice_date), str(due_date),
            client_name, f"{total_due:.2f}", "Reverse" if reverse_tax else f"{tax_rate}%",
            "Late" if overdue and status_option == "Unpaid" else "On Time", status_option
        ])

        st.success("Invoice PDF generated and uploaded successfully.")
        st.download_button("Download Invoice", data=pdf_buffer, file_name=invoice_filename, mime="application/pdf")
