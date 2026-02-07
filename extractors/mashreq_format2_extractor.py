import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


IGNORE_KEYWORDS = [
    "Account Statement", "Statement for period", "Account Number",
    "Mashreq", "Branch", "Currency", "IBAN", "Customer Number",
    "Account Type", "Dear Customer", "Page", "Balance", "Opening balance", "Closing balance"
]


def is_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def clean_text(s: str) -> str:
    if not s:
        return ""
    # remove weird multi-space and non-ascii (keeps punctuation)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_date(text: str) -> str:
    """Convert YYYY-MM-DD to DD-MM-YYYY"""
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}', text):
            year, month, day = text.split('-')
            return f"{day}-{month}-{year}"
        return text
    except:
        return ""


def to_number(text: str) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except:
        return 0.0


def extract_mashreq_format2_data(file_bytes, password=None):
    """
    Column-position extractor for Mashreq Format2 using horizontal lines for transaction boundaries
    """
    rows = []
    global_column_positions = None  # Store column positions for pages without headers

    with pdfplumber.open(BytesIO(file_bytes), password=password) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Extract horizontal lines for transaction boundaries
            lines = page.lines
            horizontal_lines = [line for line in lines if abs(line['top'] - line['bottom']) < 2 and line['width'] > 100]
            horizontal_lines.sort(key=lambda x: x['top'])
            
            # extract words with coordinates
            words = page.extract_words(use_text_flow=True)

            if not words:
                continue

            # group words by rounded top (visual rows)
            lines_dict = {}
            for w in words:
                top = round(float(w["top"]), 1)
                lines_dict.setdefault(top, []).append(w)

            # sort lines top → bottom
            sorted_lines = sorted(lines_dict.items(), key=lambda x: x[0])

            # Find header line and establish column boundaries
            header_positions = {}
            header_found = False
            
            for top, word_list in sorted_lines[:40]:  # only scan top portion of page
                texts = [w["text"].lower() for w in word_list]
                if any("date" == t or "التاريخ" in t for t in texts) and \
                   any("debit" in t or "قيود" in t for t in texts) and \
                   any("credit" in t or "دائنه" in t for t in texts):
                    for w in word_list:
                        t = w["text"].lower()
                        if "date" == t or "التاريخ" in t:
                            header_positions["date"] = float(w["x0"])
                        if "transaction" in t or "المعاملة" in t:
                            header_positions["transaction"] = float(w["x0"])
                        if "reference" in t or "المرجع" in t:
                            header_positions["reference"] = float(w["x0"])
                        if "debit" in t or "قيود" in t:
                            header_positions["debit"] = float(w["x0"])
                        if "credit" in t or "دائنه" in t:
                            header_positions["credit"] = float(w["x0"])
                        if "balance" in t or "الرصيد" in t:
                            header_positions["balance"] = float(w["x0"])
                    header_found = True
                    break

            # Use fallback positions if header not found
            if not header_found:
                if global_column_positions:
                    # Use column positions from previous page with headers
                    header_positions = global_column_positions.copy()
                    print(f"Page {page_num + 1}: Using column positions from previous page")
                else:
                    # Use default fallback positions
                    header_positions = {
                        "date": 40.0,
                        "transaction": 120.0,
                        "reference": 280.0,
                        "debit": 420.0,
                        "credit": 480.0,
                        "balance": 540.0
                    }
                    print(f"Page {page_num + 1}: Using default column positions (no header found)")
            else:
                # Store column positions for pages without headers
                global_column_positions = header_positions.copy()
                print(f"Page {page_num + 1}: Found headers, storing column positions")

            # Create strict column boundaries based on header positions
            items = sorted(header_positions.items(), key=lambda x: x[1])
            xs = [p for _, p in items]
            
            # Define strict column ranges - ADJUSTED to fix column shift issue
            if len(xs) >= 6:  # We have all 6 columns: Date, Transaction, Reference, Debit, Credit, Balance
                date_range = (0, xs[1])
                trans_range = (xs[1], xs[2])
                # SHIFT THESE COLUMNS LEFT to fix the alignment issue
                ref_range = (xs[2], xs[3] - 20)      # Reference column (shift left)
                debit_range = (xs[3] - 20, xs[4] - 20)  # Debit column (shift left) 
                credit_range = (xs[4] - 20, xs[5] - 20) # Credit column (shift left)
                balance_range = (xs[5] - 20, 9999)      # Balance column (ignore)
            else:
                # Fallback with estimated positions - ADJUSTED
                date_range = (0, 100)
                trans_range = (100, 270)
                ref_range = (270, 390)      # Adjusted reference range
                debit_range = (390, 450)    # Adjusted debit range
                credit_range = (450, 510)   # Adjusted credit range  
                balance_range = (510, 9999) # Adjusted balance range

            def get_column(x_pos):
                """Determine which column an x position belongs to"""
                if date_range[0] <= x_pos < date_range[1]:
                    return "date"
                elif trans_range[0] <= x_pos < trans_range[1]:
                    return "transaction"
                elif ref_range[0] <= x_pos < ref_range[1]:
                    return "reference"
                elif debit_range[0] <= x_pos < debit_range[1]:
                    return "debit"
                elif credit_range[0] <= x_pos < credit_range[1]:
                    return "credit"
                else:
                    return "balance"  # Ignore balance column

            # Create transaction boundaries using horizontal lines
            transaction_boundaries = []
            
            # Special handling for pages without headers - look for first transaction
            if not header_found:
                # Find the first date line on this page
                first_date_y = None
                for top, word_list in sorted_lines:
                    for w in word_list:
                        if re.match(r'^\d{4}-\d{2}-\d{2}', w["text"]):
                            first_date_y = top
                            break
                    if first_date_y:
                        break
                
                if first_date_y and horizontal_lines:
                    # Add boundary from first transaction to first horizontal line
                    first_transaction_start = first_date_y - 5
                    first_transaction_end = horizontal_lines[0]['top']
                    transaction_boundaries.append((first_transaction_start, first_transaction_end))
                    
                    # Add boundaries between consecutive horizontal lines
                    for i in range(len(horizontal_lines) - 1):
                        start_y = horizontal_lines[i]['top']
                        end_y = horizontal_lines[i + 1]['top']
                        transaction_boundaries.append((start_y, end_y))
            else:
                # Original logic for pages with headers
                # Add first transaction boundary (from opening balance to first horizontal line)
                if horizontal_lines:
                    # Find opening balance line
                    opening_balance_y = None
                    for top, word_list in sorted_lines:
                        line_text = " ".join(w["text"] for w in word_list).lower()
                        if "opening balance" in line_text:
                            opening_balance_y = top
                            break
                    
                    # Add boundary from opening balance to first horizontal line
                    if opening_balance_y:
                        first_transaction_start = opening_balance_y + 10  # Start after opening balance
                        first_transaction_end = horizontal_lines[0]['top']
                        transaction_boundaries.append((first_transaction_start, first_transaction_end))
                    
                    # Add boundaries between consecutive horizontal lines
                    for i in range(len(horizontal_lines) - 1):
                        start_y = horizontal_lines[i]['top']
                        end_y = horizontal_lines[i + 1]['top']
                        transaction_boundaries.append((start_y, end_y))
                else:
                    # Fallback: create boundaries based on date lines if no horizontal lines found
                    date_positions = []
                    for top, word_list in sorted_lines:
                        for w in word_list:
                            if re.match(r'^\d{4}-\d{2}-\d{2}', w["text"]):
                                date_positions.append(top)
                                break
                    
                    for i in range(len(date_positions)):
                        start_y = date_positions[i] - 10
                        end_y = date_positions[i + 1] - 10 if i + 1 < len(date_positions) else date_positions[i] + 100
                        transaction_boundaries.append((start_y, end_y))

            # Process each transaction boundary
            for start_y, end_y in transaction_boundaries:
                transaction_data = {
                    "date": "",
                    "transaction": "",
                    "reference": "",
                    "debit": "",
                    "credit": "",
                    "balance": ""
                }
                
                # Collect all text within this transaction boundary
                for top, word_list in sorted_lines:
                    if start_y <= top <= end_y:
                        for w in sorted(word_list, key=lambda w: w["x0"]):
                            text = w["text"].strip()
                            if not text or is_arabic(text):
                                continue
                            
                            x_pos = float(w["x0"])
                            col = get_column(x_pos)
                            
                            if col != "balance":  # Ignore balance column completely
                                if transaction_data[col]:
                                    transaction_data[col] += " " + text
                                else:
                                    transaction_data[col] = text

                # Skip if no date found (not a transaction)
                date_text = transaction_data["date"].strip()
                if not re.match(r"^\d{4}-\d{2}-\d{2}", date_text):
                    continue

                # Extract description from transaction column
                description = clean_text(transaction_data["transaction"])
                
                # Skip opening/closing balance entries
                if any(keyword in description.lower() for keyword in ['opening balance', 'closing balance', 'balance']):
                    continue
                
                # Extract reference number from reference column
                reference = clean_text(transaction_data["reference"])
                
                # Extract amounts from debit and credit columns - IGNORE BALANCE COLUMN
                debit_amount = 0.0
                credit_amount = 0.0
                
                # Process debit column - extract ONLY the first valid amount
                debit_text = transaction_data["debit"].strip()
                if debit_text:
                    # Remove any balance amounts that might have leaked in
                    debit_match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", debit_text)
                    if debit_match:
                        amount = to_number(debit_match.group(1))
                        # Only use if it's a reasonable transaction amount (not a large balance)
                        if amount < 100000:  # Reasonable transaction limit
                            debit_amount = amount
                
                # Process credit column - extract ONLY the first valid amount
                credit_text = transaction_data["credit"].strip()
                if credit_text:
                    # Remove any balance amounts that might have leaked in
                    credit_match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", credit_text)
                    if credit_match:
                        amount = to_number(credit_match.group(1))
                        # Only use if it's a reasonable transaction amount (not a large balance)
                        if amount < 100000:  # Reasonable transaction limit
                            credit_amount = amount
                
                # Create transaction record using CORRECT column logic
                # Based on your PDF: Debit column = Withdrawals, Credit column = Deposits
                transaction = {
                    "Date": parse_date(date_text),
                    "Withdrawals": debit_amount,   # Debit column = Withdrawals
                    "Deposits": credit_amount,     # Credit column = Deposits  
                    "Payee": "",
                    "Description": description,
                    "Reference Number": reference
                }
                
                # Only add if we have a valid date and at least one amount
                if transaction["Date"] and (debit_amount > 0 or credit_amount > 0):
                    rows.append(transaction)

    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Remove any remaining balance-related entries
    if not df.empty:
        df = df[~df['Description'].str.contains('balance|opening|closing', case=False, na=False)]
        # Remove transactions with no amounts
        df = df[(df['Withdrawals'] > 0) | (df['Deposits'] > 0)]
    
    # Ensure all required columns exist
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            df[col] = "" if col in ["Payee", "Description", "Reference Number"] else 0.0

    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]