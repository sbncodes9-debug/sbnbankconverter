import pdfplumber
import pandas as pd
import re
from io import BytesIO
from dateutil.parser import parse

def clean_date(text):
    try:
        return parse(text, dayfirst=True).strftime("%d-%m-%Y")
    except:
        return None

def to_number(text):
    try:
        if not text:
            return 0.0
        # Remove commas and convert to float
        return float(str(text).replace(",", "").strip())
    except:
        return 0.0

def extract_mashreq_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Try table extraction first (most reliable)
            tables = page.extract_tables()
            
            if not tables:
                continue

            for table in tables:
                # Skip header rows and process data rows
                for row in table:
                    if not row or len(row) < 4:
                        continue

                    # Skip header rows
                    if any(h in str(row[0] or "") for h in ["Date", "Reference", "Description", "Amount", "Balance"]):
                        continue

                    try:
                        # Typical Mashreq table structure:
                        # Date | Value Date | Reference Number | Description | Amount | Balance
                        date_str = row[0]
                        
                        # Parse date
                        date = clean_date(date_str) if date_str else None
                        if not date:
                            continue

                        # Description is typically in the middle columns
                        desc_parts = []
                        ref = ""
                        
                        # Collect description from columns before amount
                        for idx, col in enumerate(row[1:-2]):  # Skip first col (date) and last 2 (amount, balance)
                            if not col or not str(col).strip():
                                continue
                            
                            col_text = str(col).strip()
                            
                            # Skip dates in the format "DD Mon YYYY" (e.g., "01 Jul 2025")
                            if re.match(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}$", col_text):
                                continue
                            
                            # Extract reference number (alphanumeric, often starts with digits)
                            if re.match(r"^[A-Z0-9]{10,}$", col_text) and not re.match(r"^\d+$", col_text):
                                if not ref:
                                    ref = col_text
                                continue
                            
                            # Add non-empty, non-numeric text to description
                            if col_text and not re.match(r"^[+-]?[\d,]+\.?\d*$", col_text):
                                desc_parts.append(col_text)
                        
                        description = " ".join(desc_parts)

                        # Extract amount (second to last column, typically)
                        amount_str = row[-2] if len(row) > 1 else ""
                        amount_val = to_number(amount_str) if amount_str else 0.0

                        # Determine if it's a deposit or withdrawal based on sign
                        # Positive = Deposit, Negative = Withdrawal
                        deposits = 0.0
                        withdrawals = 0.0
                        
                        if amount_val > 0:
                            deposits = amount_val
                        elif amount_val < 0:
                            withdrawals = abs(amount_val)

                        rows.append({
                            "Date": date,
                            "Deposits": deposits,
                            "Withdrawals": withdrawals,
                            "Payee": "",
                            "Description": description.strip(),
                            "Reference Number": ref
                        })
                    except Exception as e:
                        # Skip rows that fail to parse
                        continue

    df = pd.DataFrame(rows)
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
