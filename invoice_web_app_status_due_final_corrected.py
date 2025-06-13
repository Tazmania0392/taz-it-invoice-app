
import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import tempfile
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === Configuration ===
PARENT_FOLDER_ID = "1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"
SPREADSHEET_ID = "1vBUF05rh5sF0IfoIYryJfJLqWXleAehlqXKT1pXFUHs"

# === Google Auth ===
service_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
creds = service_account.Credentials.from_service_account_info(
    service_info,
    scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
)

drive_service = build("drive", "v3", credentials=creds)
sheet_service = build("sheets", "v4", credentials=creds)

# === Helpers ===
def ensure_client_folder(client_name):
    results = drive_service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{client_name}' and '{PARENT_FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]
    metadata = {
        "name": client_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [PARENT_FOLDER_ID]
    }
    folder = drive_service.files().create(body=metadata, fields="id").execute()
    return folder["id"]

def ensure_invoices_sheet_exists():
    try:
        metadata = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = [s["properties"]["title"] for s in metadata["sheets"]]
        if "Invoices" not in sheets:
            sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={"requests": [{"addSheet": {"properties": {"title": "Invoices"}}}]}
            ).execute()
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range="Invoices!A1:H1",
                valueInputOption="RAW",
                body={"values": [["Date", "Invoice #", "Client Name", "Amount (AWG)", "Tax Rate", "Status", "Due Date", "Drive Link"]]}
            ).execute()
    except Exception as e:
        st.error(f"Sheet creation error: {e}")

# === UI ===
st.title("🧾 Taz-IT Invoice App")
col1, col2 = st.columns(2)
with col1:
    invoice_number = st.text_input("Invoice Number")
    invoice_date = st.date_input("Invoice Date", value=date.today())
    due_date = st.date_input("Payment Due Date", value=date.today())
with col2:
    client_name = st.text_input("Client Name")
    client_address = st.text_area("Client Address")
    client_phone = st.text_input("Client Phone")

tax_rate = st.number_input("Tax Rate (%)", value=12.0)
status = st.selectbox("Invoice Status", ["Unpaid", "Paid"])
st.markdown("#### Reverse Tax Calculator")
reverse_total = st.number_input("Total incl. tax (optional)", value=0.0)
if reverse_total > 0:
    pre_tax = reverse_total / (1 + tax_rate / 100)
    st.write(f"Pre-Tax Subtotal: {pre_tax:.2f} AWG")

st.markdown("### Line Items")
df = st.data_editor(pd.DataFrame(columns=["Description", "Units", "Qty", "Rate (AWG)"]), num_rows="dynamic")

# === Generate ===
if st.button("Generate & Upload Invoice"):
    if df.dropna(subset=["Description"]).empty:
        st.warning("Please enter at least one line item.")
    else:
        df = df.fillna(0)
        df["Total"] = df["Units"].astype(float) * df["Qty"].astype(float) * df["Rate (AWG)"].astype(float)
        subtotal = df["Total"].sum()
        tax = subtotal * (tax_rate / 100)
        total = subtotal + tax

        late = datetime.today().date() > due_date and status == "Unpaid"
        status_display = "Late" if late else status

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, "INVOICE", ln=True, align="C")
        pdf.set_font("Arial", size=10)
        pdf.ln(5)
        pdf.cell(100, 8, "Taz-IT Solutions", ln=1)
        pdf.cell(100, 8, "Client: " + client_name, ln=1)
        pdf.cell(100, 8, "Date: " + str(invoice_date), ln=1)
        pdf.cell(100, 8, "Due: " + str(due_date), ln=1)
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(60, 8, "Description", 1)
        pdf.cell(20, 8, "Units", 1)
        pdf.cell(20, 8, "Qty", 1)
        pdf.cell(30, 8, "Rate", 1)
        pdf.cell(30, 8, "Total", 1)
        pdf.ln()
        pdf.set_font("Arial", size=10)
        for _, row in df.iterrows():
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
        client_folder_id = ensure_client_folder(client_name)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name)
            media = MediaFileUpload(tmp.name, mimetype="application/pdf")
            file_metadata = {
                "name": filename,
                "parents": [client_folder_id]
            }
            uploaded_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()
            file_id = uploaded_file.get("id")
            file_url = f"https://drive.google.com/file/d/{file_id}/view"

        ensure_invoices_sheet_exists()
        sheet_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Invoices!A2",
            valueInputOption="USER_ENTERED",
            body={"values": [[str(invoice_date), invoice_number, client_name, f"{total:.2f}", tax_rate, status_display, str(due_date), file_url]]}
        ).execute()

        st.success("✅ Invoice uploaded and logged.")
        st.markdown(f"[View in Drive]({file_url})", unsafe_allow_html=True)
