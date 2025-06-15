
# Taz IT Invoice Generator - Full Application with Client Management, Google Sheets, PDF, and Reverse Tax

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
CLIENT_SHEET_NAME = "Clients"
sheet_service = build("sheets", "v4", credentials=creds)

# Ensure Clients sheet exists
try:
    meta = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if CLIENT_SHEET_NAME not in titles:
        sheet_service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": CLIENT_SHEET_NAME}}}]}
        ).execute()
        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{CLIENT_SHEET_NAME}!A1:D1",
            valueInputOption="RAW",
            body={"values": [["Client Name", "Company Name", "Address", "Phone"]]}
        ).execute()
except Exception as e:
    st.error(f"Client sheet setup error: {e}")

# Load clients
client_data = sheet_service.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID,
    range=f"{CLIENT_SHEET_NAME}!A2:D"
).execute().get("values", [])

clients_dict = {row[0]: {"company": row[1], "address": row[2], "phone": row[3]} for row in client_data if len(row) == 4}

st.title("Taz IT Invoice Generator")

# Client selection
selected_client = st.selectbox("Select Existing Client (optional)", ["New Client"] + list(clients_dict.keys()))

if selected_client != "New Client":
    client_info = clients_dict[selected_client]
    client_name = selected_client
    company_name = client_info["company"]
    client_address = client_info["address"]
    client_phone = client_info["phone"]
else:
    client_name = st.text_input("Client Name")
    company_name = st.text_input("Company Name")
    client_address = st.text_area("Client Address")
    client_phone = st.text_input("Client Phone")

# Save new client
if selected_client == "New Client" and client_name and company_name and client_address and client_phone:
    if client_name not in clients_dict:
        sheet_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{CLIENT_SHEET_NAME}!A2",
            valueInputOption="USER_ENTERED",
            body={"values": [[client_name, company_name, client_address, client_phone]]}
        ).execute()

# Edit/Delete existing client
if selected_client != "New Client":
    with st.expander("Edit Selected Client Info"):
        new_name = st.text_input("Edit Client Name", value=client_name)
        new_company = st.text_input("Edit Company Name", value=company_name)
        new_address = st.text_area("Edit Address", value=client_address)
        new_phone = st.text_input("Edit Phone", value=client_phone)

        name_conflict = new_name != client_name and new_name in clients_dict

        if st.button("Update Client Info"):
            if name_conflict:
                st.warning("Client name already exists. Please choose a unique name.")
            else:
                client_values = [new_name, new_company, new_address, new_phone]
                client_data_updated = [client_values if row[0] == client_name else row for row in client_data]
                sheet_service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{CLIENT_SHEET_NAME}!A2:D",
                    valueInputOption="RAW",
                    body={"values": client_data_updated}
                ).execute()
                st.success(f"✅ Client info for '{new_name}' updated!")

        if st.button("❌ Delete Client"):
            updated_data = [row for row in client_data if row[0] != client_name]
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{CLIENT_SHEET_NAME}!A2:D",
                valueInputOption="RAW",
                body={"values": updated_data}
            ).execute()
            st.success(f"🗑️ Client '{client_name}' deleted. Please refresh the app.")

invoice_date = st.date_input("Invoice Date", datetime.today())
due_date = st.date_input("Payment Due Date")
tax_rate = st.number_input("Tax Rate (%)", value=12.0)

custom_total = st.number_input("Total Price incl. Tax (AWG) [optional]", value=0.0)
subtotal = custom_total / (1 + tax_rate / 100) if custom_total > 0 else None
if subtotal:
    st.info(f"Calculated Subtotal: {subtotal:.2f} AWG")

manual_invoice = st.checkbox("Enter Invoice Number Manually")
if manual_invoice:
    invoice_number = st.text_input("Invoice Number")
else:
    def ensure_invoices_sheet_exists(sheet_service, spreadsheet_id):
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

    def get_next_invoice_number(sheet_service, spreadsheet_id):
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Invoices!B2:B"
        ).execute()
        values = result.get("values", [])
        if values:
            last = max([int(v[0]) for v in values if v and v[0].isdigit()])
            return str(last + 1)
        return "1001"

    ensure_invoices_sheet_exists(sheet_service, SPREADSHEET_ID)
    invoice_number = get_next_invoice_number(sheet_service, SPREADSHEET_ID)

st.markdown("### Line Items")
item_df = st.data_editor(
    pd.DataFrame(columns=["Description", "Units", "Qty", "Rate (AWG)"]),
    num_rows="dynamic"
)

status = st.selectbox("Invoice Status", ["Unpaid", "Paid"])
if datetime.today().date() > due_date and status == "Unpaid":
    status = "Late"

class InvoicePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(10, 10, 10)

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_xy(0, 12)
        self.cell(0, 10, "INVOICE", ln=True, align="C")
        self.line(10, 22, 200, 22)
        self.image("tazit_logo_pdf.png", x=165, y=10, w=35)

    def company_info(self):
        self.set_font("Helvetica", "", 10)
        self.set_xy(10, 25)
        for line in [
            "Taz IT Solutions", "Pos Chikito 99B", "Oranjestad, Aruba",
            "(+297) 699-7692 | jcroes@tazitsolution.com"
        ]:
            self.cell(100, 5, line, ln=1)

    def client_info(self, name, company, address, phone, invoice_number, invoice_date):
        self.set_y(50)
        self.set_font("Helvetica", "", 10)
        self.set_x(10)
        self.cell(100, 6, f"Bill To: {name} ({company})", ln=0)
        self.set_x(130)
        self.cell(60, 6, f"Invoice #: {invoice_number}", ln=1)
        self.set_x(10)
        self.cell(100, 6, address, ln=0)
        self.set_x(130)
        self.cell(60, 6, f"Date: {invoice_date.strftime('%d-%b-%Y')}", ln=1)
        self.set_x(10)
        self.cell(100, 6, phone, ln=1)

    def line_items_table(self, items):
        self.ln(5)
        self.set_fill_color(200, 50, 50)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        col_widths = [60, 20, 20, 30, 30]
        headers = ["Description", "Units", "Qty", "Rate", "Total"]
        for h, w in zip(headers, col_widths):
            self.cell(w, 6, h, 1, 0, 'C', True)
        self.ln()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(0, 0, 0)
        for i, row in enumerate(items):
            self.cell(col_widths[0], 6, row["desc"], 1)
            self.cell(col_widths[1], 6, str(row["units"]), 1, 0, 'C')
            self.cell(col_widths[2], 6, str(row["qty"]), 1, 0, 'C')
            self.cell(col_widths[3], 6, f"{row['rate']:.2f}", 1, 0, 'R')
            self.cell(col_widths[4], 6, f"{row['total']:.2f}", 1, 0, 'R')
            self.ln()

    def totals_table(self, subtotal, tax, tax_rate, total):
        self.ln(4)
        self.set_font("Helvetica", "", 10)
        label_x = 110
        value_x = 140
        row_height = 6
        col_width = 30

        self.set_x(label_x)
        self.cell(col_width, row_height, "Subtotal", border=1)
        self.set_x(value_x)
        self.cell(col_width, row_height, f"{subtotal:.2f} AWG", border=1, ln=1, align='R')

        self.set_x(label_x)
        self.cell(col_width, row_height, f"Tax ({tax_rate:.0f}%)", border=1)
        self.set_x(value_x)
        self.cell(col_width, row_height, f"{tax:.2f} AWG", border=1, ln=1, align='R')

        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(230, 230, 230)
        self.set_x(label_x)
        self.cell(col_width, row_height, "Total", border=1, fill=True)
        self.set_x(value_x)
        self.cell(col_width, row_height, f"{total:.2f} AWG", border=1, ln=1, align='R', fill=True)

    def footer_section(self):
        self.ln(6)
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 5, "Thank you for your business!", ln=1)
        self.cell(0, 5, "Payment due within 14 days.", ln=1)
        self.ln(3)
        self.set_font("Helvetica", "", 10)
        for line in [
            "Bank Payment Info:",
            "Bank: Aruba Bank",
            "Account Name: Joshua Croes",
            "Account Number: 3066850190",
            "SWIFT/BIC: ARUBAWAW",
            "Currency: AWG"
        ]:
            self.cell(0, 5, line, ln=1)

# Generate and upload PDF
if st.button("Generate & Upload Invoice"):
    valid_df = item_df.dropna(subset=["Description"])
    if valid_df.empty:
        st.warning("Please enter at least one line item.")
    else:
        try:
            valid_df["Total"] = valid_df["Units"].astype(float) * valid_df["Qty"].astype(float) * valid_df["Rate (AWG)"].astype(float)
            subtotal_final = subtotal if subtotal else valid_df["Total"].sum()
            tax = subtotal_final * (tax_rate / 100)
            total = subtotal_final + tax

            pdf = InvoicePDF()
            pdf.add_page()
            pdf.company_info()
            pdf.client_info(client_name, company_name, client_address, client_phone, invoice_number, invoice_date)

            items = [{
                "desc": row["Description"],
                "units": float(row["Units"]),
                "qty": float(row["Qty"]),
                "rate": float(row["Rate (AWG)"]),
                "total": row["Total"]
            } for _, row in valid_df.iterrows()]

            pdf.line_items_table(items)
            pdf.totals_table(subtotal_final, tax, tax_rate, total)
            pdf.footer_section()

            filename = f"Invoice_{invoice_number}_{client_name.title().replace(' ', '')}.pdf"
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
                body={"values": [[
                    str(invoice_date),
                    invoice_number,
                    client_name,
                    f"{total:.2f}",
                    tax_rate,
                    f"https://drive.google.com/file/d/{file_id}/view",
                    status
                ]]}
            ).execute()

            st.success("✅ Invoice uploaded and logged successfully!")
            st.markdown(f"[📄 View Invoice PDF](https://drive.google.com/file/d/{file_id}/view)", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ Upload or logging failed: {e}")
