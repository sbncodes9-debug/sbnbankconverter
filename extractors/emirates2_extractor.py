import pdfplumber
import pandas as pd
import re
from io import BytesIO
from dateutil.parser import parse
from datetime import datetime

# Convert 02NOV25 → 02-11-2025
def convert_date(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
    try:
        return parse(raw, dayfirst=True).strftime("%d-%m-%Y")
    except:
        return ""

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


def extract_emirates2_data(pdf_bytes):
    rows = []
    # Read PDF tables
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                # Process all rows
                for row in table:
                    if not row:
                        continue

                    # Fixed positions: Date in 1, Narration in 2, Debit in 3, Credit in 4
                    txn_date = convert_date(row[1]) if len(row) > 1 else ""

                    narration = str(row[2] or "").strip() if len(row) > 2 else ""
                    debit_amt = to_float(row[3]) if len(row) > 3 else 0.0
                    credit_amt = to_float(row[4]) if len(row) > 4 else 0.0
                    debit_amt = 0.0
                    credit_amt = 0.0

                    # Extract amount from narration
                    amounts = re.findall(amount_regex, narration)
                    if amounts:
                        amount_val = to_float(amounts[-1])
                        final_narration = re.sub(amount_regex, "", narration).strip()
                    else:
                        amount_val = 0.0
                        final_narration = narration

                    # Determine amounts
                    if debit_amt > 0:
                        withdrawals = debit_amt
                        deposits = 0.0
                    elif credit_amt > 0:
                        deposits = credit_amt
                        withdrawals = 0.0
                    elif amount_val > 0:
                        # Use amount from description, assume withdrawal if description has withdrawal keywords
                        desc_text = final_narration.upper()
                        is_withdrawal = any(k in desc_text for k in ["POS-PURCHASE", "PURCHASE", "DEBIT", "CHQ"])
                        if is_withdrawal:
                            withdrawals = amount_val
                            deposits = 0.0
                        else:
                            deposits = amount_val
                            withdrawals = 0.0
                    else:
                        continue  # No amount

                    rows.append({
                        "Date": txn_date,
                        "Withdrawals": withdrawals,
                        "Deposits": deposits,
                        "Payee": "",
                        "Description": final_narration,
                        "Reference Number": ""
                    })

    text_lines = []
    amount_regex = r"[\d,]+\.\d{2}"

    # --- Deposit Conditions ---
    deposit_keywords = [
        "REFUND", "CUSTOMER CREDIT", "TRANSFER",
        "CREDIT", "POS-REFUNDS", "SETT", "REMIT"
    ]

    # --- Withdrawal Conditions ---
    withdrawal_keywords = [
        "POS-PURCHASE", "PURCHASE", "INWARD",
        "CHQ", "DEBIT", "CLEARING", "FEE", "CHARGES", "VALUE ADDED TAX"
    ]

    description_parts = []
    i = 0
    while i < len(text_lines):
        line = text_lines[i].strip()

        # Skip noise/headers
        if any(x in line for x in [
            "Statement", "Page", "Balance", "Description", "Debits",
            "Credits", "Brought Forward", "Carried Forward",
            "Forward", "Emirates", "Dubai", "United Arab", "UAE",
            "Tax Registration", "Registered", "Head Office", "Commercial",
            "Account", "CURRENT", "DIRHAM", "Branch", "from", "to",
            "Monthly", "Interest"
        ]):
            i += 1
            continue

        date_match = re.search(date_regex, line)
        if date_match:
            date_str = date_match.group(1)
            date = convert_date(date_str)
            
            if date:
                # Process the collected description_parts
                amount_float = 0.0
                deposits = 0.0
                withdrawals = 0.0
                final_description = []
                
                for desc_line in description_parts:
                    amounts = re.findall(amount_regex, desc_line)
                    if amounts:
                        amount_val = amounts[-1].replace(",", "")
                        try:
                            amount_float = float(amount_val)
                        except:
                            amount_float = 0.0
                        # Clean desc_line
                        for amt in amounts:
                            desc_line = desc_line.replace(amt, "").replace("Cr", "").replace("Dr", "")
                        desc_line = desc_line.strip()
                    if desc_line:
                        final_description.append(desc_line)
                
                # Determine deposit/withdrawal
                desc_text = " ".join(final_description).upper()
                is_deposit = any(k in desc_text for k in deposit_keywords)
                is_withdrawal = any(k in desc_text for k in withdrawal_keywords)
                
                if is_deposit and not is_withdrawal:
                    deposits = amount_float
                elif is_withdrawal and not is_deposit:
                    withdrawals = amount_float
                else:
                    deposits = amount_float  # fallback
                
                if deposits > 0 or withdrawals > 0:
                    rows.append({
                        "Date": date,
                        "Withdrawals": withdrawals,
                        "Deposits": deposits,
                        "Payee": "",
                        "Description": " ".join(final_description).strip(),
                        "Reference Number": ""
                    })
            
            description_parts = []  # Reset for next transaction
        else:
            description_parts.append(line)

    # Create DataFrame with safeguards
    if rows:
        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame(columns=["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"])
    
    # Ensure all columns exist
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            if col in ["Withdrawals", "Deposits"]:
                df[col] = 0.0
            else:
                df[col] = ""
    
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]