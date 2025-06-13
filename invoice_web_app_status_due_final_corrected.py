
from fpdf import FPDF

class InvoicePDF(FPDF):
    def header(self):
        # Logo
        self.image("tazit_logo_pdf.png", x=170, y=10, w=30)
        self.set_font("Arial", "B", 16)
        self.ln(30)
        self.cell(0, 10, "INVOICE", border=0, ln=True, align="C")

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

    def company_info(self):
        self.set_font("Arial", "", 10)
        self.cell(100, 5, "Taz-IT Solutions", ln=True)
        self.cell(100, 5, "Pos Chikito 99B", ln=True)
        self.cell(100, 5, "Oranjestad, Aruba", ln=True)
        self.cell(100, 5, "(+297) 699-7692 | jcroes@tazitsolution.com", ln=True)

    def client_info(self, name, address, phone, invoice_num, date_str):
        self.set_font("Arial", "", 10)
        self.cell(100, 5, f"Bill To: {name}", ln=0)
        self.cell(80, 5, f"Invoice #: {invoice_num}", ln=1, align="R")
        self.cell(100, 5, address, ln=0)
        self.cell(80, 5, f"Date: {date_str}", ln=1, align="R")
        self.cell(100, 5, phone, ln=1)

    def add_table(self, df, subtotal, tax, total, tax_rate):
        self.set_font("Arial", "B", 10)
        self.set_fill_color(200, 0, 0)
        self.set_text_color(255)
        self.cell(60, 8, "Description", 1, 0, "C", 1)
        self.cell(20, 8, "Units", 1, 0, "C", 1)
        self.cell(20, 8, "Qty", 1, 0, "C", 1)
        self.cell(30, 8, "Rate", 1, 0, "C", 1)
        self.cell(30, 8, "Total", 1, 1, "C", 1)

        self.set_font("Arial", "", 10)
        self.set_text_color(0)
        for _, row in df.iterrows():
            self.cell(60, 8, str(row["Description"]), 1)
            self.cell(20, 8, str(row["Units"]), 1)
            self.cell(20, 8, str(row["Qty"]), 1)
            self.cell(30, 8, str(row["Rate (AWG)"]), 1)
            self.cell(30, 8, f"{row['Total']:.2f}", 1, ln=1)

        self.ln(5)
        self.set_x(140)
        self.cell(30, 8, "Subtotal", 1)
        self.cell(30, 8, f"{subtotal:.2f} AWG", 1, ln=1)
        self.set_x(140)
        self.cell(30, 8, f"Tax ({tax_rate:.0f}%)", 1)
        self.cell(30, 8, f"{tax:.2f} AWG", 1, ln=1)
        self.set_x(140)
        self.cell(30, 8, "Total", 1)
        self.cell(30, 8, f"{total:.2f} AWG", 1, ln=1)

    def add_payment_terms(self):
        self.ln(10)
        self.set_font("Arial", "I", 10)
        self.cell(0, 5, "Thank you for your business!", ln=1)
        self.cell(0, 5, "Payment due within 14 days.", ln=1)

    def add_bank_details(self):
        self.ln(5)
        self.set_font("Arial", "", 10)
        self.cell(0, 5, "Bank Payment Info:", ln=1)
        self.cell(0, 5, "Bank: Aruba Bank", ln=1)
        self.cell(0, 5, "Account Name: Joshua Croes", ln=1)
        self.cell(0, 5, "Account Number: 3066850190", ln=1)
        self.cell(0, 5, "SWIFT/BIC: ARUBAWAW", ln=1)
        self.cell(0, 5, "Currency: AWG", ln=1)
    
