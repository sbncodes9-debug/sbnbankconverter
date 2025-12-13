import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO
from dateutil.parser import parse

# Convert 02NOV25 → 02-11-2025
def convert_date(raw):
    try:
        return parse(raw, dayfirst=True).strftime("%d-%m-%Y")
    except:
        return None


def extract_emirates2_data(pdf_bytes):

    rows = []
    text_lines = []

    # Read PDF text
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        text = page.get_text("text")
        text_lines.extend(text.split("\n"))
        if t:
            text_lines.extend(t.split("\n"))

    date_regex = r"^\d{2}[A-Z]{3}\d{2}"      # 02NOV25
    amount_regex = r"[\d,]+\.\d{2}"

    i = 0
    while i < len(text_lines):
        line = text_lines[i].strip()

        # Skip noise/headers
        if any(x in line for x in [
            "Statement", "Page", "Balance", "Date", "Description", "Debits",
            "Credits", "Brought Forward", "Carried Forward",
            "Forward", "Emirates", "Dubai", "United Arab", "UAE",
            "Tax Registration", "Registered", "Head Office", "Commercial",
            "Account", "CURRENT", "DIRHAM", "Branch", "from", "to",
            "Monthly", "Interest"
        ]):
            i += 1
            continue

        # Detect transaction start (date pattern at line start)
        if re.match(date_regex, line):
            date_str = line.split()[0]  # Extract just the date
            date = convert_date(date_str) if date_str else None
            
            if not date:
                i += 1
                continue
            
            # This line contains date and possibly start of description
            description_parts = []
            
            # Get everything after the date
            rest_of_line = line[len(date_str):].strip()
            if rest_of_line:
                description_parts.append(rest_of_line)
            
            # Look ahead for continuation lines (until we find amounts)
            i += 1
            deposits = 0.0
            withdrawals = 0.0
            
            while i < len(text_lines):
                next_line = text_lines[i].strip()
                
                if not next_line:
                    i += 1
                    continue
                
                # Check if this line starts with a new date
                if re.match(date_regex, next_line):
                    break
                
                # Skip footer lines
                if any(x in next_line for x in ["CARRIED", "BROUGHT", "Emirates NBD", "Date Description"]):
                    i += 1
                    break
                
                # Look for amounts in this line
                # Pattern: amount1 amount2Cr (e.g., "27.75 518,802.21Cr")
                # We want the LAST amounts (at end of line), not amounts in the middle
                amounts = re.findall(amount_regex, next_line)
                
                if amounts and len(amounts) >= 1:
                    amount_val = amounts[0].replace(",", "")
                    try:
                        amount_float = float(amount_val)
                    except:
                        amount_float = 0.0

                    desc_text = " ".join(description_parts).upper()

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

                    is_deposit = any(k in desc_text for k in deposit_keywords)
                    is_withdrawal = any(k in desc_text for k in withdrawal_keywords)

                    # Apply logic
                    if is_deposit and not is_withdrawal:
                        deposits = amount_float

                    elif is_withdrawal and not is_deposit:
                        withdrawals = amount_float

                    else:
                        # fallback: if nothing matches, treat single amount as deposit
                        deposits = amount_float

                    
                    # Add this line to description (minus the balance at end)
                    # Remove amounts from the line for description
                    desc_line = next_line
                    for amt in amounts:
                        desc_line = desc_line.replace(amt, "").replace("Cr", "").replace("Dr", "")
                    desc_line = desc_line.strip()
                    
                    if desc_line:
                        description_parts.append(desc_line)
                    
                    i += 1
                    break
                else:
                    # No amounts yet, this is still description
                    description_parts.append(next_line)
                    i += 1
            
            # Only add if we have a valid date
            if date and (deposits > 0 or withdrawals > 0):
                rows.append({
                    "Date": date,
                    "Withdrawals": withdrawals,
                    "Deposits": deposits,
                    "Payee": "",
                    "Description": " ".join(description_parts).strip(),
                    "Reference Number": ""
                })
        else:
            i += 1

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
