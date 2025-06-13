import streamlit as st

try:
    st.write("App is starting...")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import pandas as pd
    from fpdf import FPDF
    from datetime import date
    from io import BytesIO
    import os
    import tempfile

    st.write("Libraries loaded.")

    GOOGLE_SERVICE_ACCOUNT = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
    SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
    st.write("Secrets loaded.")

    # continue setup...

except Exception as e:
    st.error(f"Startup failed: {e}")

# invoice_web_app.py
import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
from fpdf import FPDF
import os
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- SETUP ---
GOOGLE_SERVICE_ACCOUNT = st.secrets["GOOGLE_SERVICE_ACCOUNT"]
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]

creds = service_account.Credentials.from_service_account_info(GOOGLE_SERVICE_ACCOUNT, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)
sheet_service = build("sheets", "v4", credentials=creds)

# --- LAYOUT ---
st.set_page_config("Taz-IT Invoicing App")
st.title("🧾 Taz-IT Invoice Generator")

col1, col2 = st.columns(2)
with col1:
    client_name = st.text_input("Client Name")
    client_address = st.text_input("Client Address")
    client_phone = st.text_input("Client Phone")
with col2:
    invoice_number = st.text_input("Invoice Number")
    invoice_date = st.date_input("Invoice Date", value=date.today())
    due_date = st.date_input("Due Date", value=invoice_date)

tax_rate = st.number_input("Tax %", value=12.0)
reverse_tax = st.checkbox("Apply Reverse Tax")
total_price_after_tax = 0.0
if reverse_tax:
    total_price_after_tax = st.number_input("Enter total incl. tax (optional)", value=0.0)

excel_file = st.file_uploader("Upload Excel Line Items", type="xlsx")
status = st.selectbox("Invoice Status", ["Unpaid", "Paid"])

def read_excel(file):
    df = pd.read_excel(file)
    df = df.dropna(subset=["Description"])
    df["Units"] = df["Units"].astype(int)
    df["Qty"] = df["Qty"].astype(int)
    df["Rate"] = df["Rate"].astype(float)
    df["Total"] = df["Units"] * df["Qty"] * df["Rate"]
    return df

def generate_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.image("tazit_logo_pdf.png", 150, 10, 40)

    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "INVOICE", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(100, 10, "Taz-IT Solutions")
    pdf.cell(100, 10, f"Invoice #: {invoice_number}", ln=True)
    pdf.cell(100, 10, "Pos Chikito 99B, Aruba")
    pdf.cell(100, 10, f"Date: {invoice_date.strftime('%Y-%m-%d')}", ln=True)
    pdf.cell(100, 10, "(+297) 699-7692 | jcroes@tazitsolution.com")
    pdf.cell(100, 10, f"Due: {due_date.strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(10)
    pdf.cell(100, 10, f"Bill To: {client_name}")
    pdf.cell(100, 10, f"{client_address}", ln=True)
    pdf.cell(100, 10, client_phone, ln=True)
    pdf.ln(10)

    pdf.set_fill_color(200, 0, 0)
    pdf.set_text_color(255)
    for col in ["Description", "Units", "Qty", "Rate", "Total"]:
        pdf.cell(38 if col == "Description" else 30, 10, col, 1, 0, 'C', True)
    pdf.ln()
    pdf.set_text_color(0)

    for _, row in df.iterrows():
        pdf.cell(38, 10, str(row["Description"]), 1)
        pdf.cell(30, 10, str(row["Units"]), 1)
        pdf.cell(30, 10, str(row["Qty"]), 1)
        pdf.cell(30, 10, f"{row['Rate']:.2f}", 1)
        pdf.cell(30, 10, f"{row['Total']:.2f}", 1)
        pdf.ln()

    subtotal = df["Total"].sum()
    tax = subtotal * (tax_rate / 100)
    total = subtotal + tax

    for label, value in [("Subtotal", subtotal), (f"Tax ({tax_rate:.0f}%)", tax), ("Total", total)]:
        pdf.cell(158)
        pdf.cell(30, 10, label, 1)
        pdf.cell(30, 10, f"{value:.2f} AWG", 1, ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", "I", 11)
    pdf.multi_cell(0, 10, "Thank you for your business!\n\nPayment due within 14 days.\n\nFor any questions, contact us at support@tazitsolution.com")
    pdf.ln(5)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, "Bank Payment Info:\nBank: Aruba Bank\nAccount Name: Joshua Croes\nAccount Number: 3066850190\nSWIFT/BIC: ARUBAWAW\nCurrency: AWG")

    pdf_output = BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output, total

def upload_to_drive(file, filename, client_name):
    folders = drive_service.files().list(q="mimeType='application/vnd.google-apps.folder' and name='Invoices' and trashed=false").execute().get("files", [])
    parent_id = folders[0]["id"] if folders else drive_service.files().create(body={"name": "Invoices", "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
    client_folders = drive_service.files().list(q=f"'{parent_id}' in parents and name='{client_name}' and trashed=false").execute().get("files", [])
    folder_id = client_folders[0]["id"] if client_folders else drive_service.files().create(body={"name": client_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}, fields="id").execute()["id"]

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp.write(file.read())
    temp.close()
    media = MediaFileUpload(temp.name, mimetype="application/pdf")
    uploaded = drive_service.files().create(body={"name": filename, "parents": [folder_id]}, media_body=media, fields="id").execute()
    os.remove(temp.name)
    return f"https://drive.google.com/file/d/{uploaded['id']}/view"

def log_to_sheet(date, invoice_no, name, amount, status, link):
    values = [[str(date), str(invoice_no), name, f"{amount:.2f} AWG", status, link]]
    sheet_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="Invoices!A2",
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

if st.button("Generate Invoice"):
    if excel_file is not None:
        df = read_excel(excel_file)
        pdf_file, total_amt = generate_pdf(df)
        file_name = f"Invoice_{invoice_number}_{client_name}.pdf"
        link = upload_to_drive(pdf_file, file_name, client_name)
        log_to_sheet(invoice_date, invoice_number, client_name, total_amt, status, link)
        st.success("Invoice created and uploaded ✅")
        st.markdown(f"[View PDF Invoice]({link})")
    else:
        st.error("Please upload an Excel file with line items.")
