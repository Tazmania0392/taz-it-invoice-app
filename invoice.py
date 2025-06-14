
import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import tempfile
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load credentials
service_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = service_account.Credentials.from_service_account_info(
    service_info,
    scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
)

SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
PARENT_FOLDER_ID = st.secrets["PARENT_FOLDER_ID"]

def ensure_invoices_sheet_exists(sheet_service, spreadsheet_id):
    try:
        meta = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        titles = [s["properties"]["title"] for s in meta["sheets"]]
        if "Invoices" not in titles:
            sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": "Invoices"}}}]}
            ).execute()
            headers = [["Date", "Invoice #", "Client Name", "Amount (AWG)", "Tax Rate", "Drive File Link", "Status"]]
            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Invoices!A1:G1",
                valueInputOption="RAW",
                body={"values": headers}
            ).execute()
    except Exception as e:
        st.error(f"Sheet error: {e}")

def get_next_invoice_number(sheet_service, spreadsheet_id):
    try:
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Invoices!B2:B"
        ).execute()
        values = result.get("values", [])
        if values:
            last = max([int(v[0]) for v in values if v and v[0].isdigit()])
            return str(last + 1)
        return "1001"
    except:
        return "1001"

class InvoicePDF(FPDF):
    def header(self):
        self.image("tazit_logo_pdf.png", x=170, y=10, w=30)
        self.set_font("Arial", "B", 16)
        self.cell(0, 15, "INVOICE", ln=True, align="C")

    def company_info(self):
        self.set_font("Arial", "", 10)
        for line in [
            "Taz-IT Solutions", "Pos Chikito 99B", "Oranjestad, Aruba",
            "(+297) 699-7692 | jcroes@tazitsolution.com"
        ]:
            self.cell(100, 6, line, ln=1)

    def client_info(self, name, address, phone, invoice_number, invoice_date):
        self.set_y(50)
        self.set_font("Arial", "", 10)
        self.set_x(10)
        self.cell(100, 6, f"Bill To: {name}", ln=0)
        self.set_x(130)
        self.cell(60, 6, f"Invoice #: {invoice_number}", ln=1)
        self.set_x(10)
        self.cell(100, 6, address, ln=0)
        self.set_x(130)
        self.cell(60, 6, f"Date: {invoice_date.strftime('%d-%b-%Y')}", ln=1)
        self.set_x(10)
        self.cell(100, 6, phone, ln=1)
        self.ln(5)

    def line_items_table(self, items):
        self.set_fill_color(200, 0, 0)
        self.set_text_color(255)
        self.set_font("Arial", "B", 10)
        self.cell(60, 8, "Description", 1, 0, 'C', True)
        self.cell(20, 8, "Units", 1, 0, 'C', True)
        self.cell(20, 8, "Qty", 1, 0, 'C', True)
        self.cell(30, 8, "Rate", 1, 0, 'C', True)
        self.cell(30, 8, "Total", 1, 1, 'C', True)
        self.set_font("Arial", "", 10)
        self.set_text_color(0)
        for row in items:
            self.cell(60, 8, row["desc"], 1)
            self.cell(20, 8, str(row["units"]), 1)
            self.cell(20, 8, str(row["qty"]), 1)
            self.cell(30, 8, f"{row['rate']:.2f}", 1)
            self.cell(30, 8, f"{row['total']:.2f}", 1, 1)

    def totals_table(self, subtotal, tax, tax_rate, total):
        self.ln(3)
        self.set_x(140)
        self.cell(30, 8, "Subtotal", 1)
        self.cell(30, 8, f"{subtotal:.2f} AWG", 1, ln=1)
        self.set_x(140)
        self.cell(30, 8, f"Tax ({tax_rate:.0f}%)", 1)
        self.cell(30, 8, f"{tax:.2f} AWG", 1, ln=1)
        self.set_x(140)
        self.cell(30, 8, "Total", 1)
        self.cell(30, 8, f"{total:.2f} AWG", 1, ln=1)

    def footer_section(self):
        self.set_y(-45)
        self.set_font("Arial", "I", 10)
        self.cell(0, 6, "Thank you for your business!", ln=1)
        self.cell(0, 6, "Payment due within 14 days.", ln=1)
        self.ln(5)
        self.set_font("Arial", "", 10)
        for line in [
            "Bank Payment Info:",
            "Bank: Aruba Bank",
            "Account Name: Joshua Croes",
            "Account Number: 3066850190",
            "SWIFT/BIC: ARUBAWAW",
            "Currency: AWG"
        ]:
            self.cell(0, 6, line, ln=1)

# UI
st.title("🧾 Taz-IT Invoice Generator")

client_name = st.text_input("Client Name")
client_address = st.text_area("Client Address")
client_phone = st.text_input("Client Phone")
invoice_date = st.date_input("Invoice Date", datetime.today())
due_date = st.date_input("Payment Due Date")
tax_rate = st.number_input("Tax Rate (%)", value=12.0)

st.markdown("### Line Items")
item_df = st.data_editor(
    pd.DataFrame(columns=["Description", "Units", "Qty", "Rate (AWG)"]),
    num_rows="dynamic"
)

status = st.selectbox("Invoice Status", ["Unpaid", "Paid"])
if datetime.today().date() > due_date and status == "Unpaid":
    status = "Late"

if st.button("Generate & Upload Invoice"):
    valid_df = item_df.dropna(subset=["Description"])
    if valid_df.empty:
        st.warning("Please enter at least one line item.")
    else:
        try:
            valid_df["Total"] = valid_df["Units"].astype(float) * valid_df["Qty"].astype(float) * valid_df["Rate (AWG)"].astype(float)
            subtotal = valid_df["Total"].sum()
            tax = subtotal * (tax_rate / 100)
            total = subtotal + tax

            sheet_service = build("sheets", "v4", credentials=creds)
            ensure_invoices_sheet_exists(sheet_service, SPREADSHEET_ID)
            invoice_number = get_next_invoice_number(sheet_service, SPREADSHEET_ID)

            pdf = InvoicePDF()
            pdf.add_page()
            pdf.company_info()
            pdf.client_info(client_name, client_address, client_phone, invoice_number, invoice_date)

            items = [{
                "desc": row["Description"],
                "units": float(row["Units"]),
                "qty": float(row["Qty"]),
                "rate": float(row["Rate (AWG)"]),
                "total": row["Total"]
            } for _, row in valid_df.iterrows()]

            pdf.line_items_table(items)
            pdf.totals_table(subtotal, tax, tax_rate, total)
            pdf.footer_section()

            filename = f"invoice_{invoice_number}_{client_name.title().replace(' ', '')}.pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                pdf.output(tmp.name)

                drive_service = build("drive", "v3", credentials=creds)
                media = MediaFileUpload(tmp.name, mimetype="application/pdf")
                file_metadata = {"name": filename}
                if PARENT_FOLDER_ID:
                    file_metadata["parents"] = [PARENT_FOLDER_ID]

                uploaded_file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id"
                ).execute()
                file_id = uploaded_file.get("id")

            sheet_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Invoices!A2",
                valueInputOption="USER_ENTERED",
                body={"values": [[str(invoice_date), invoice_number, client_name, f"{total:.2f}", tax_rate, f"https://drive.google.com/file/d/{file_id}/view", status]]}
            ).execute()

            st.success("✅ Invoice uploaded and logged successfully!")
            st.markdown(f"[📄 View Invoice PDF](https://drive.google.com/file/d/{file_id}/view)", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ Upload or logging failed: {e}")
