
def ensure_invoices_sheet_exists(sheet_service, spreadsheet_id):
    # Check if 'Invoices' tab exists, create if not
    try:
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

            # Add headers to the new sheet
            headers = [["Date", "Invoice #", "Client Name", "Amount (AWG)", "Tax Rate", "Drive File Link", "Status"]]
            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Invoices!A1:G1",
                valueInputOption="RAW",
                body={"values": headers}
            ).execute()
    except Exception as e:
        print("Failed to verify or create 'Invoices' sheet:", e)
