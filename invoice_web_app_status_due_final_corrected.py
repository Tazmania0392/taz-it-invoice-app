class InvoicePDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 16)
        self.cell(0, 10, "INVOICE", ln=True, align="C")
        # Add logo in the top-right corner
        self.image("logo.png", x=160, y=10, w=30)  # Adjust path and size as needed

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
            self.cell(col_widths[3], 8, f"{row['Rate']:.2f} AWG", 1, 0, 'R')
            self.cell(col_widths[4], 8, f"{row['Total']:.2f} AWG", 1, 0, 'R')
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
