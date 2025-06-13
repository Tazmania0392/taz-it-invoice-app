
import streamlit as st
import pandas as pd
from datetime import date
from pdf_layout_updated_based_on_design import InvoicePDF

# Sample data
df = pd.DataFrame([{
    "Description": "License services",
    "Units": 1,
    "Qty": 1,
    "Rate (AWG)": 500.00,
    "Total": 500.00
}])

# Generate PDF
pdf = InvoicePDF()
pdf.add_page()
pdf.company_info()
pdf.ln(10)
pdf.client_info(
    name="Bon Vibe",
    address="Kerkstraat 4, Aruba",
    phone="297 746 3522",
    invoice_num="1001",
    date_str=date.today().strftime("%d-%b-%Y")
)
pdf.ln(5)
pdf.add_table(df, subtotal=500.00, tax=60.00, total=560.00, tax_rate=12)
pdf.add_payment_terms()
pdf.add_bank_details()

# Save to file
pdf.output("/mnt/data/Invoice_1001_BonVibe.pdf")
