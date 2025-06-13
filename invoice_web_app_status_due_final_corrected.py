
import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import tempfile
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load credentials from Streamlit secrets
service_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = service_account.Credentials.from_service_account_info(
    service_info,
    scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
)

# Google Drive and Sheet config
SPREADSHEET_ID = "1vBUF05rh5sF0IfoIYryJfJLqWXleAehlqXKT1pXFUHs"
PARENT_FOLDER_ID = "1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"

def ensure_invoices_sheet_exists(sheet_service, spreadsheet_id):
    try:
        sheets_metadata = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_titles = [s["properties"]["title"] for s in sheets_metadata["sheets"]]
        if "Invoices" not in sheet_titles:
            requests = [{
                "addSheet": {
                    "properties": {
                        "title": "Invoices",
                        "gridProperties": {"rowCount": 1000, "columnCount": 7}
                    }
                }
            }]
            sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
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

# Streamlit UI
st.title("🧾 Taz-IT Invoice Generator")

invoice_number = st.text_input("Invoice Number")
invoice_date = st.date_input("Invoice Date", datetime.today())
client_name = st.text_input("Client Name")
client_address = st.text_area("Client Address")
client_phone = st.text_input("Client Phone")

tax_rate = st.number_input("Tax Rate (%)", value=12.0)
due_date = st.date_input("Payment Due Date")

st.markdown("### Line Items")
item_df = st.data_editor(pd.DataFrame(columns=["Description", "Units", "Qty", "Rate (AWG)"]), num_rows="dynamic")

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

            # PDF Generation
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(200, 10, "INVOICE", ln=True, align="C")
            pdf.set_font("Arial", size=10)
            pdf.cell(100, 8, "Taz-IT Solutions", ln=1)
            pdf.cell(100, 8, f"Client: {client_name}", ln=1)
            pdf.cell(100, 8, f"Date: {invoice_date}", ln=1)
            pdf.cell(100, 8, f"Due: {due_date}", ln=1)
            pdf.ln(5)
            pdf.set_font("Arial", "B", 10)
            pdf.cell(60, 8, "Description", 1)
            pdf.cell(20, 8, "Units", 1)
            pdf.cell(20, 8, "Qty", 1)
            pdf.cell(30, 8, "Rate", 1)
            pdf.cell(30, 8, "Total", 1)
            pdf.ln()
            pdf.set_font("Arial", size=10)
            for _, row in valid_df.iterrows():
                pdf.cell(60, 8, str(row["Description"]), 1)
                pdf.cell(20, 8, str(row["Units"]), 1)
                pdf.cell(20, 8, str(row["Qty"]), 1)
                pdf.cell(30, 8, str(row["Rate (AWG)"]), 1)
                pdf.cell(30, 8, f"{row['Total']:.2f}", 1)
                pdf.ln()
            pdf.ln(5)
            pdf.cell(130)
            pdf.cell(30, 8, "Subtotal", 1)
            pdf.cell(30, 8, f"{subtotal:.2f} AWG", 1, ln=1)
            pdf.cell(130)
            pdf.cell(30, 8, f"Tax ({tax_rate:.0f}%)", 1)
            pdf.cell(30, 8, f"{tax:.2f} AWG", 1, ln=1)
            pdf.cell(130)
            pdf.cell(30, 8, "Total", 1)
            pdf.cell(30, 8, f"{total:.2f} AWG", 1, ln=1)

            filename = f"Invoice_{invoice_number}_{client_name.replace(' ', '')}.pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                pdf.output(tmp.name)

                drive_service = build("drive", "v3", credentials=creds)
                media = MediaFileUpload(tmp.name, mimetype="application/pdf")

                file_metadata = {"name": filename, "parents": ["1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"]}

                uploaded_file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id"
                ).execute()
                file_id = uploaded_file.get("id")

            # Log to Sheet
            sheet_service = build("sheets", "v4", credentials=creds)
            ensure_invoices_sheet_exists(sheet_service, SPREADSHEET_ID)
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="Invoices!A2",
                valueInputOption="USER_ENTERED",
                body={"values": [[str(invoice_date), invoice_number, client_name, f"{total:.2f}", tax_rate, f"https://drive.google.com/file/d/{file_id}/view", status]]}
            ).execute()

            st.success("Invoice uploaded and logged successfully!")
            st.markdown(f"[View Invoice PDF](https://drive.google.com/file/d/{file_id}/view)", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ Upload or logging failed: {e}")
