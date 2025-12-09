import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def clean_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        return float(text.replace(",", "").strip())
    except:
        return 0.0


def extract_adcb2_data(file_bytes):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Try to extract tables from the page
            tables = page.extract_tables()
            
            if not tables:
                continue

            for table in tables:
                # Skip header rows and process data rows
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 8:
                        continue

                    # Skip header rows (look for "Sr No", "Date", "Description" etc.)
                    if any(header in str(row[0] or "") for header in ["Sr No", "Sr.", "Date", "Description"]):
                        continue

                    try:
                        # Extract columns: Sr No | Date | Value Date | Bank Ref | Customer Ref | Description | Debit | Credit | Balance
                        # Column indices may vary, so we'll be flexible
                        sr_no = row[0]
                        date_str = row[1]
                        
                        # Parse date
                        date = parse_date(date_str) if date_str else ""
                        if not date:
                            continue

                        # Description is typically in the middle columns (before amounts)
                        # Find description by looking for text that's not a number, date, or bank reference
                        desc_parts = []
                        ref = ""
                        
                        for col in row[2:-3]:  # Skip sr_no, date, and last 3 cols (likely debit/credit/balance)
                            if not col or not col.strip():
                                continue
                            
                            col_text = col.strip()
                            
                            # Skip dates (pattern: DD-MMM-YYYY)
                            if re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$", col_text):
                                continue
                            
                            # Extract reference number (10+ digit number, often prefixed with bank code)
                            if re.search(r"\d{10,}", col_text):
                                # Capture the longest digit sequence as reference
                                matches = re.findall(r"\d{10,}", col_text)
                                if matches and not ref:
                                    ref = matches[0]
                                # Skip this column if it's purely a reference number or bank reference
                                if re.match(r"^[A-Z]{3}\d{6,}$|^\d{10,}$", col_text):
                                    continue
                            
                            # Add to description if it's actual text content
                            if col_text and not re.match(r"^[\d\s\.\-]+$", col_text):
                                desc_parts.append(col_text)
                        
                        description = " ".join(desc_parts)

                        # Extract numeric amounts from the last columns
                        # Typically: Debit Amount | Credit Amount | Balance
                        debit = 0.0
                        credit = 0.0
                        balance = None

                        # Get the last 3 numeric columns (Debit, Credit, Balance)
                        numeric_cols = row[-3:]
                        
                        if len(numeric_cols) >= 3:
                            debit = to_number(numeric_cols[0]) if numeric_cols[0] else 0.0
                            credit = to_number(numeric_cols[1]) if numeric_cols[1] else 0.0
                            balance = to_number(numeric_cols[2]) if numeric_cols[2] else None
                        elif len(numeric_cols) == 2:
                            debit = to_number(numeric_cols[0]) if numeric_cols[0] else 0.0
                            credit = to_number(numeric_cols[1]) if numeric_cols[1] else 0.0

                        rows.append({
                            "Date": date,
                            "Withdrawals": debit,
                            "Deposits": credit,
                            "Payee": "",
                            "Description": clean_text(description),
                            "Reference Number": ref
                        })
                    except Exception as e:
                        # Skip rows that fail to parse
                        continue

    df = pd.DataFrame(rows)
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
