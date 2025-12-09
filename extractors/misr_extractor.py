import pdfplumber
import pandas as pd
from io import BytesIO
from datetime import datetime

def clean(t):
    if not t:
        return ""
    return str(t).strip()

def parse_date(t):
    try:
        return datetime.strptime(t, "%d/%m/%Y").strftime("%d-%m-%Y")
    except:
        return ""

def to_number(t):
    try:
        return float(t.replace(",", "").strip())
    except:
        return 0.0

def extract_misr_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:

            tables = page.extract_tables()

            for table in tables:
                for row in table:

                    # Skip header junk rows
                    joined = " ".join([clean(c) for c in row]).lower()
                    if "balance" in joined or "description" in joined or "txnrefno" in joined:
                        continue

                    if len(row) < 7:
                        continue

                    # Column mapping STRICT
                    balance = clean(row[0])
                    credit  = clean(row[1])
                    debit   = clean(row[2])
                    value_date = clean(row[3])   # ignored
                    ref_no  = clean(row[4])
                    desc    = clean(row[5])
                    date    = clean(row[6])

                    tran_date = parse_date(date)

                    if not tran_date:
                        continue

                    rows.append({
                        "Date": tran_date,
                        "Withdrawals": to_number(debit),
                        "Deposits": to_number(credit),
                        "Payee": "",
                        "Description": desc,
                        "Reference Number": ref_no
                    })

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"
        ])

    return df
