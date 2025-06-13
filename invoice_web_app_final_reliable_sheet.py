
def ensure_invoices_sheet_exists(sheet_service, spreadsheet_id):
    # Check if 'Invoices' tab exists, create if not
    sheets_metadata = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_titles = [s["properties"]["title"] for s in sheets_metadata["sheets"]]

    if "Invoices" not in sheet_titles:
        requests = [{
            "addSheet": {
                "properties": {
                    "title": "Invoices",
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": 6
                    }
                }
            }
        }]
        sheet_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        # Add headers
        headers = [["Date", "Invoice #", "Client Name", "Amount (AWG)", "Tax Rate", "Drive File Link", "Status"]]
        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Invoices!A1:F1",
            valueInputOption="RAW",
            body={"values": headers}
        ).execute()



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

invoice_number = st.text_input("Invoice Number", value="1001")
invoice_date = st.date_input("Invoice Date", value=datetime.today())

client_name = st.text_input("Client Name", value="Bon Vibe")
client_address = st.text_input("Client Address", value="Kerkstraat 4, Aruba")
client_phone = st.text_input("Client Phone", value="297 746 3522")

st.subheader("Tax Settings")
tax_rate_percent = st.number_input("Tax rate (%)", min_value=0.0, max_value=100.0, value=12.0, step=0.1)
tax_rate = tax_rate_percent / 100

st.markdown("### 🎯 Reverse Tax Calculator")
target_total = st.number_input("Enter total incl. tax (optional)", min_value=0.0, format="%.2f")
suggested_rate = None
if target_total:
    base = target_total / (1 + tax_rate)
    tax = target_total - base
    st.write(f"Subtotal: **{base:.2f} AWG**, Tax: **{tax:.2f} AWG**")
    suggested_rate = round(base, 2)

st.subheader("Line Items")
default_data = pd.DataFrame([{"Description": "License services", "Units": 1, "Qty": 1, "Rate (AWG)": suggested_rate if suggested_rate else 0.0}])
item_df = st.data_editor(default_data, num_rows="dynamic", use_container_width=True)

def get_drive_service():
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=[
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets"
    ])
    return build("drive", "v3", credentials=creds), creds

def create_folder_if_not_exists(service, name, parent=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent:
        query += f" and '{parent}' in parents"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent:
        file_metadata["parents"] = [parent]
    file = service.files().create(body=file_metadata, fields="id").execute()
    return file.get("id")

def generate_pdf_bytes(invoice_number, invoice_date, client_name, client_address, client_phone, df, tax_rate):
    pdf = FPDF()
    pdf.add_page()

    logo_path = "tazit_logo_pdf.png"
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=160, y=10, w=30)

    pdf.set_y(45)
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "INVOICE", ln=True, align="C")

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

    tax = subtotal * tax_rate
    grand_total = subtotal + tax
    pdf.ln(3)
    for label, value in [("Subtotal", subtotal), (f"Tax ({int(tax_rate*100)}%)", tax), ("Total", grand_total)]:
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

    return pdf.output(dest="S").encode("latin-1"), subtotal, tax, subtotal + tax

def log_to_sheet(creds, invoice_number, invoice_date, client_name, total_awg, tax_rate, drive_file_id):
    from googleapiclient.discovery import build
    sheet_service = build("sheets", "v4", credentials=creds)

    spreadsheet_id = create_sheet_if_not_exists(creds)
    ensure_invoices_sheet_exists(sheet_service, spreadsheet_id)
    sheet_range = "Invoices!A:F"
    values = [[
        invoice_date.strftime("%Y-%m-%d"),
        invoice_number,
        client_name,
        f"{total_awg:.2f}",
        f"{int(tax_rate * 100)}%",
        f"https://drive.google.com/file/d/{drive_file_id}"
    ]]
    body = {"values": values}
    sheet_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=sheet_range,
        valueInputOption="USER_ENTERED", body=body).execute()

# BEGIN: Fixed create_sheet_if_not_exists
# BEGIN: Updated for stability
def create_sheet_if_not_exists(creds):
    import time
    drive = build("drive", "v3", credentials=creds)

    # Delete broken versions if needed (manual step)
    query = "name='Invoice_Log' and mimeType='application/vnd.google-apps.spreadsheet'"
    result = drive.files().list(q=query, fields="files(id)").execute()
    if result["files"]:
        return result["files"][0]["id"]

    # Create fresh Google Sheet
    file_metadata = {
        "name": "Invoice_Log",
        "mimeType": "application/vnd.google-apps.spreadsheet", "parents": ["1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"]
    }
    file = drive.files().create(body=file_metadata, fields="id").execute()
    time.sleep(2)  # allow time to fully provision sheet
    return file.get("id")
# END
    drive = build("drive", "v3", credentials=creds)

    # Search for the sheet in Drive
    query = "name='Invoice_Log' and mimeType='application/vnd.google-apps.spreadsheet'"
    result = drive.files().list(q=query, fields="files(id)").execute()
    if result["files"]:
        return result["files"][0]["id"]

    # If not found, create new Google Sheet
    file_metadata = {
        "name": "Invoice_Log",
        "mimeType": "application/vnd.google-apps.spreadsheet", "parents": ["1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"]
    }
    file = drive.files().create(body=file_metadata, fields="id").execute()
    return file.get("id")
# END
    drive = build("drive", "v3", credentials=creds)
    query = "name='Invoice_Log' and mimeType='application/vnd.google-apps.spreadsheet'"
    result = drive.files().list(q=query, fields="files(id)").execute()
    if result["files"]:
        return result["files"][0]["id"]
    file_metadata = {"name": "Invoice_Log", "mimeType": "application/vnd.google-apps.spreadsheet", "parents": ["1GwKcp0mPEo-PlBHiHthxblTMmMoCUxQo"]}
    file = drive.files().create(body=file_metadata, fields="id").execute()
    return file.get("id")

if st.button("Generate & Upload Invoice"):
    
        status = st.selectbox("Invoice Status", ["Unpaid", "Paid"], index=0)
        due_date = st.date_input("Payment Due Date")
        today = datetime.today().date()
        late = today > due_date and status == "Unpaid"
        status = "Late" if late else status


    valid_df = item_df.dropna(subset=["Description"])
    if valid_df.empty:
        st.warning("Please enter at least one line item.")
    else:
        filename = f"Invoice_{invoice_number}_{client_name.replace(' ', '')}.pdf"
        drive_service, creds = get_drive_service()

        # Main folder
        parent_folder = create_folder_if_not_exists(drive_service, "Invoices")
        client_folder = create_folder_if_not_exists(drive_service, client_name.replace(" ", ""), parent=parent_folder)

        pdf_bytes, subtotal, tax, total = generate_pdf_bytes(invoice_number, invoice_date, client_name, client_address, client_phone, valid_df, tax_rate)

        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf")
        file_metadata = {"name": filename, "parents": [client_folder]}
        file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        file_id = file["id"]

        log_to_sheet(creds, invoice_number, invoice_date, client_name, total, tax_rate, file_id)

        st.success(f"✅ Invoice uploaded to Google Drive and logged (File ID: {file_id})")

        st.subheader("🔍 PDF Preview")
        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
        st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px"></iframe>', unsafe_allow_html=True)
        st.download_button("📄 Download PDF", data=pdf_bytes, file_name=filename, mime="application/pdf")


        st.subheader("📤 Export Invoice Log (Admin)")
        if st.button("Download Invoice Log as Excel"):
            import gspread
            import pandas as pd
            from gspread_dataframe import get_as_dataframe
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(spreadsheet_id)
            worksheet = sh.worksheet("Invoices")
            df = get_as_dataframe(worksheet, evaluate_formulas=True).dropna(how="all")
            df.to_excel("/tmp/invoice_log_export.xlsx", index=False)
            with open("/tmp/invoice_log_export.xlsx", "rb") as f:
                st.download_button("📥 Download Excel", f.read(), file_name="invoice_log.xlsx")

        if st.button("Download Invoice Log as PDF"):
            import gspread
            from fpdf import FPDF
            import pandas as pd
            from gspread_dataframe import get_as_dataframe
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(spreadsheet_id)
            worksheet = sh.worksheet("Invoices")
            df = get_as_dataframe(worksheet, evaluate_formulas=True).dropna(how="all")
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)
            col_widths = [25, 25, 40, 25, 20, 60, 20]
            headers = df.columns.tolist()
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 8, str(header), border=1)
            pdf.ln()
            for _, row in df.iterrows():
                for i, cell in enumerate(row):
                    pdf.cell(col_widths[i], 8, str(cell), border=1)
                pdf.ln()
            pdf.output("/tmp/invoice_log_export.pdf")
            with open("/tmp/invoice_log_export.pdf", "rb") as f:
                st.download_button("📥 Download PDF", f.read(), file_name="invoice_log.pdf")


        st.subheader("📋 Outstanding Invoices")
        import gspread
        from gspread_dataframe import get_as_dataframe
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)
        worksheet = sh.worksheet("Invoices")
        df = get_as_dataframe(worksheet, evaluate_formulas=True).dropna(how="all")

        filtered = df[df["Status"].isin(["Unpaid", "Late"])]
        st.dataframe(filtered)
