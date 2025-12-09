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


def format_date(d):
    try:
        dt = datetime.strptime(d.strip(), "%d/%m/%Y")
        return dt.strftime("%d-%m-%Y")
    except:
        return ""


def extract_wio_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        lines = []
        for p in pdf.pages:
            text = p.extract_text()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(line)

    # Detect statement type: check for "CREDIT STATEMENT" to differentiate
    full_text = "\n".join(lines)
    is_credit_statement = "CREDIT STATEMENT" in full_text.upper() or "CREDIT LIMIT" in full_text.upper()

    if is_credit_statement:
        # Credit card statement parsing
        # Pattern: Date | Ref Number | Description | Card Number | Amount
        # Example: 13/10/2025 | P3583315453 | Withdrawal.com | ****$243 | -66.60
        cc_line_re = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+([A-Z0-9]+)\s+(.+?)\s+(\*{4}\$?\d+)\s+([+-]?[\d,]+\.?\d*)$")
        
        for line in lines:
            m = cc_line_re.match(line)
            if not m:
                continue

            date_raw = m.group(1)
            ref = m.group(2)
            desc_raw = m.group(3).strip()
            # card_num = m.group(4)  # Optional: store card number if needed
            amount_raw = m.group(5)

            amt = to_float(amount_raw)
            deposit = amt if amt > 0 else 0.0
            withdrawal = abs(amt) if amt < 0 else 0.0

            rows.append({
                "Date": format_date(date_raw),
                "Deposits": deposit,
                "Withdrawals": withdrawal,
                "Payee": "",
                "Description": desc_raw,
                "Reference Number": ref
            })
    else:
        # Account statement parsing (original logic)
        # detect start of transaction line
        line_re = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(P\d+)\s*(.*)$")

        for line in lines:
            m = line_re.match(line)
            if not m:
                continue

            date_raw = m.group(1)
            ref = m.group(2)
            rest = m.group(3).strip()

            # ✅ safe split from right
            parts = rest.rsplit(None, 2)

            if len(parts) == 3:
                desc_raw, amount_raw, balance_raw = parts
            elif len(parts) == 2:
                desc_raw, amount_raw = parts
            else:
                continue

            amt = to_float(amount_raw)
            deposit = amt if amt > 0 else 0.0
            withdrawal = abs(amt) if amt < 0 else 0.0

            rows.append({
                "Date": format_date(date_raw),
                "Deposits": deposit,
                "Withdrawals": withdrawal,
                "Payee": "",
                "Description": desc_raw.strip(),
                "Reference Number": ref
            })

    df = pd.DataFrame(rows)
    df = df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
    return df

