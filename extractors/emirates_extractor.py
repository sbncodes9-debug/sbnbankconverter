import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def to_float(val):
    if not val:
        return 0.0
    val = str(val).replace(",", "").strip()
    try:
        return float(val)
    except:
        return 0.0


def format_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d-%m-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def extract_emirates_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    if not row:
                        continue

                    # Skip header row
                    if "Transaction" in str(row[0]):
                        continue

                    # Make sure minimum columns are present
                    if len(row) < 5:
                        continue

                    # ✅ Correct fixed positions
                    txn_date = format_date(row[0])         # Transaction Date
                    narration = str(row[2] or "").strip()  # Narration
                    debit_amt = to_float(row[3])           # Debit
                    credit_amt = to_float(row[4])          # Credit

                    # Reference number from narration
                    ref_match = re.search(r"(AE\d+)", narration)
                    reference = ref_match.group(1) if ref_match else ""

                    rows.append({
                        "Date": txn_date,                       # ✅ Transaction Date only
                        "Deposits": credit_amt,                 # ✅ Credit → Deposits
                        "Withdrawals": debit_amt,               # ✅ Debit → Withdrawals
                        "Payee": "",
                        "Description": narration,               # ✅ Proper Narration
                        "Reference Number": reference
                    })

    df = pd.DataFrame(rows)
    df = df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
    return df

