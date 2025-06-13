import streamlit as st
import pandas as pd
from fpdf import FPDF
from io import BytesIO
from datetime import date

# --- PAGE SETUP ---
st.set_page_config("Taz-IT Invoice Generator")
st.title("🧾 Simple Taz-IT Invoice Generator")

# --- INPUT FIELDS ---
st.subheader("Client Info")
client_name = st.text_input("Client Name")
client_address = st.text_input("Client Address")
invoice_number = st.text_input("Invoice Number")
date_today = st.date_input("Invoice Date", value=date.today())
tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, value=12.0)

st.subheader("Invoice Line Items")
excel_file = st.file_uploader("Upload Excel File", type=["xlsx"])

# --- HELPER FUNCTIONS ---
def read_excel(file):
    df = pd.read_excel(file)
    df = df.dropna(subset=["Description"])
    df["Units"] = df["Units"].astype(int)
    df["Qty"] = df["Qty"].astype(int)
    df["Rate"] = df["Rate"].astype(float)
    df["Total"] = df["Units"] * df["Qty"] * df["Rate"]
    return df

def generate_pdf(df, client_name, client_address, invoice_number, date_today, tax_rate):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, "INVOICE", ln=True, align="C")
    pdf.ln(10)
    pdf.cell(100, 10, f"Client: {client_name}")
    pdf.cell(100, 10, f"Invoice #: {invoice_number}", ln=True)
    pdf.cell(100, 10, f"Address: {client_address}")
    pdf.cell(100, 10, f"Date: {date_today}", ln=True)
    pdf.ln(10)

    # Table header
    for col in ["Description", "Units", "Qty", "Rate", "Total"]:
        pdf.cell(38 if col == "Description" else 30, 10, col, 1, 0, 'C')
    pdf.ln()

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

    pdf.ln(5)
    pdf.cell(158)
    pdf.cell(30, 10, "Subtotal", 1)
    pdf.cell(30, 10, f"{subtotal:.2f} AWG", 1, ln=True)
    pdf.cell(158)
    pdf.cell(30, 10, f"Tax ({tax_rate:.0f}%)", 1)
    pdf.cell(30, 10, f"{tax:.2f} AWG", 1, ln=True)
    pdf.cell(158)
    pdf.cell(30, 10, "Total", 1)
    pdf.cell(30, 10, f"{total:.2f} AWG", 1, ln=True)

    pdf_output = BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

# --- GENERATE PDF ---
if st.button("Generate Invoice"):
    if excel_file and client_name and invoice_number:
        try:
            df = read_excel(excel_file)
            pdf_file = generate_pdf(df, client_name, client_address, invoice_number, date_today, tax_rate)
            st.success("Invoice generated successfully!")
            st.download_button("Download Invoice", data=pdf_file, file_name=f"Invoice_{invoice_number}.pdf")
        except Exception as e:
            st.error(f"Failed to generate invoice: {e}")
    else:
        st.warning("Please fill all fields and upload an Excel file.")
