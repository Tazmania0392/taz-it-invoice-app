import streamlit as st
import pandas as pd
from fpdf import FPDF
from datetime import datetime, date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile
import os
import io

# --- Google Drive Setup ---
SERVICE_ACCOUNT_JSON = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
INVOICE_FOLDER_ID = "1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"
SHEET_ID = "1vBUF05rh5sF0IfoIYryJfJLqWXleAehlqXKT1pXFUHs"

def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def get_sheets_service():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)

# --- PDF Generation Class ---
class InvoicePDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 16)
        self.cell(0, 10, "INVOICE", ln=True, align="C")

    def add_company_info(self):
        self.set_font("Arial", "", 10)
        self.cell(100, 5, "Taz-IT Solutions", ln=True)
        self.cell(100, 5, "Pos Chikito 99B", ln=True)
        self.cell(100, 5, "Oranjestad, Aruba", ln=True)
        self.cell(100, 5, "(+297) 699-7692 | jcroes@tazitsolution.com", ln=True)
        self.ln(5)

    def add_client_info(self, name, address, phone, invoice_no, invoice_date, due_date):
        self.set_font("Arial", "", 10)
        self.cell(100, 5, f"Bill To: {name}", ln=0)
        self.cell(100, 5, f"Invoice #: {invoice_no}", ln=1)
        self.cell(100, 5, address, ln=0)
        self.cell(100, 5, f"Date: {invoice_date}", ln=1)
        self.cell(100, 5, phone, ln=0)
        self.cell(100, 5, f"Due: {due_date}", ln=1)
        self.ln(5)

    def add_table(self, df):
        self.set_fill_color(200, 0, 0)
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 10)
        headers = ["Description", "Units", "Qty", "Rate", "Total"]
        col_widths = [60, 20, 20, 30, 30]
        for i in range(len(headers)):
            self.cell(col_widths[i], 8, headers[i], 1, 0, 'C', 1)
        self.ln()

        self.set_fill_color(255, 255, 255)
        self.set_text_color(0, 0, 0)
        self.set_font("Arial", "", 10)
        for _, row in df.iterrows():
            self.cell(col_widths[0], 8, str(row["Description"]), 1)
            self.cell(col_widths[1], 8, str(row["Units"]), 1, 0, 'C')
            self.cell(col_widths[2], 8, str(row["Qty"]), 1, 0, 'C')
            self.cell(col_widths[3], 8, f"{row['Rate']:.2f}", 1, 0, 'R')
            self.cell(col_widths[4], 8, f"{row['Total']:.2f}", 1, 0, 'R')
            self.ln()

    def add_summary(self, subtotal, tax, total):
        self.ln(3)
        labels = ["Subtotal", f"Tax (12%)", "Total"]
        values = [f"{subtotal:.2f} AWG", f"{tax:.2f} AWG", f"{total:.2f} AWG"]
        for i in range(3):
            self.cell(130)
            self.cell(30, 8, labels[i], 1)
            self.cell(30, 8, values[i], 1, ln=1, align='R')

    def add_footer(self):
        self.ln(10)
        self.set_font("Arial", "I", 9)
        self.multi_cell(0, 5, "Thank you for your business!\nPayment due within 14 days.\n\nBank Payment Info:\nBank: Aruba Bank\nAccount Name: Joshua Croes\nAccount Number: 3066850190\nSWIFT/BIC: ARUBAWAW\nCurrency: AWG")

# --- Streamlit UI ---
st.title("📄 Taz-IT Invoice Generator")

client_name = st.text_input("Client Name", "Bon Vibe")
client_address = st.text_input("Client Address", "Kerkstraat 4, Aruba")
client_phone = st.text_input("Client Phone", "297 746 3522")
invoice_number = st.text_input("Invoice Number", "1001")
invoice_date = st.date_input("Invoice Date", date.today())
due_date = st.date_input("Payment Due Date", date.today())
tax_rate = st.number_input("Tax %", value=12.0)

excel_file = st.file_uploader("Upload Excel Line Items", type=["xlsx"])
status = st.selectbox("Invoice Status", ["Unpaid", "Paid"])

if st.button("Generate Invoice"):
    if excel_file is not None:
        df = pd.read_excel(excel_file)
        df = df.dropna(subset=["Description"])
        df["Total"] = df["Qty"] * df["Rate"]
        subtotal = df["Total"].sum()
        tax = subtotal * (tax_rate / 100)
        total = subtotal + tax

        # Generate PDF
        pdf = InvoicePDF()
        pdf.add_page()
        pdf.add_company_info()
        pdf.add_client_info(client_name, client_address, client_phone, invoice_number, invoice_date.strftime("%d-%b-%Y"), due_date.strftime("%d-%b-%Y"))
        pdf.add_table(df)
        pdf.add_summary(subtotal, tax, total)
        pdf.add_footer()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            tmp_path = tmp_file.name

        # Upload to Drive
        drive_service = get_drive_service()
        client_folder = None
        response = drive_service.files().list(q=f"'{INVOICE_FOLDER_ID}' in parents and name='{client_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id)").execute()
        if response['files']:
            client_folder = response['files'][0]['id']
        else:
            file_metadata = {
                'name': client_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [INVOICE_FOLDER_ID]
            }
            folder = drive_service.files().create(body=file_metadata, fields='id').execute()
            client_folder = folder['id']

        filename = f"Invoice_{invoice_number}_{client_name.replace(' ', '')}.pdf"
        media = MediaFileUpload(tmp_path, mimetype='application/pdf')
        file_metadata = {"name": filename, "parents": [client_folder]}
        file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()

        # Log to Sheets
        sheets_service = get_sheets_service()
        values = [[str(invoice_date), invoice_number, client_name, f"{total:.2f}", f"{tax_rate:.2f}%", status]]
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range="Invoices!A2",
            valueInputOption="USER_ENTERED",
            body={"values": values}
        ).execute()

        st.success(f"✅ Invoice uploaded and logged.")
        st.download_button("⬇️ Download Invoice", data=open(tmp_path, "rb"), file_name=filename, mime="application/pdf")
