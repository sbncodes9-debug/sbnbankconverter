import pdfplumber
import pandas as pd
import re
from io import BytesIO
from dateutil.parser import parse

def clean_date(text):
    try:
        # Handle YYYY-MM-DD format (like 2021-06-24)
        if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
            return parse(text).strftime("%d-%m-%Y")
        # Handle other formats with dayfirst=True
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

def extract_mashreq_data(file_bytes, password=None):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes), password=password) as pdf:
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

                        # Extract amounts: look for columns with +/- signs or numeric values
                        # Strategy: scan columns for amounts and check for +/- indicators
                        # Exclude last column (balance) from amount detection
                        deposits = 0.0
                        withdrawals = 0.0
                        
                        # Find all numeric columns (amounts) - exclude last column (balance)
                        numeric_cols = []
                        for idx, col in enumerate(row[:-1]):  # Skip last column (balance)
                            col_text = str(col).strip() if col else ""
                            if col_text:
                                # Check for +/- sign or numeric pattern
                                if re.match(r"^[+-]?[\d,]+\.?\d*$", col_text):
                                    try:
                                        val = to_number(col_text)
                                        numeric_cols.append((idx, col_text, val))
                                    except:
                                        pass
                        
                        # Process numeric columns to find deposits and withdrawals
                        for col_idx, col_text, val in numeric_cols:
                            # Check for explicit +/- signs
                            if col_text.startswith('+'):
                                deposits = val
                            elif col_text.startswith('-'):
                                withdrawals = abs(val)
                            # If no sign, use the first two numeric columns found (debit, credit pattern)
                            elif withdrawals == 0.0 and deposits == 0.0:
                                withdrawals = val  # First amount is withdrawal
                            elif withdrawals > 0.0 and deposits == 0.0:
                                deposits = val  # Second amount is deposit

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
