import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except:
        return ""


def extract_adcb_cc_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:

        current = None
        desc_buffer = []

        for page in pdf.pages:
            lines = page.extract_text().split("\n")

            for line in lines:
                line = line.strip()

                # Skip empty or junk
                if not line:
                    continue

                # Match transaction date start
                if re.match(r"^\d{2}/\d{2}/\d{4}", line):

                    # Save previous transaction
                    if current:
                        current["Description"] = " ".join(desc_buffer).strip()
                        rows.append(current)

                    desc_buffer = []

                    # ---- Extract date ----
                    date = parse_date(line[:10])

                    # ---- Extract amount ----
                    amount_match = re.search(r"([\d,]+\.\d{2})(\s*CR)?$", line)

                    debit = 0.0
                    credit = 0.0

                    if amount_match:
                        amt = float(amount_match.group(1).replace(",", ""))

                        if amount_match.group(2):  # has "CR"
                            credit = amt
                        else:
                            debit = amt

                    # ---- Extract description text ----
                    desc_part = re.sub(r"^\d{2}/\d{2}/\d{4}", "", line)
                    desc_part = re.sub(r"[\d,]+\.\d{2}(\s*CR)?$", "", desc_part).strip()

                    if desc_part:
                        desc_buffer.append(desc_part)

                    current = {
                        "Date": date,
                        "Withdrawals": debit,
                        "Deposits": credit,
                        "Payee": "",
                        "Description": "",
                        "Reference Number": ""
                    }

                else:
                    # Continuation of description
                    if current:
                        # Skip footer junk
                        if re.search(r"balance|outstanding|page|\[1 ", line, re.I):
                            continue

                        desc_buffer.append(line)

        # Save last transaction
        if current:
            current["Description"] = " ".join(desc_buffer).strip()
            rows.append(current)

    return pd.DataFrame(rows)
