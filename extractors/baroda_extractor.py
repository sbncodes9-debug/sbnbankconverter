import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def is_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def clean_text(s: str) -> str:
    if not s:
        return ""
    # remove weird multi-space and non-ascii (keeps punctuation)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_date(text: str) -> str:
    """Convert DD/MM/YYYY to DD-MM-YYYY"""
    try:
        if re.match(r'^\d{2}/\d{2}/\d{4}', text):
            day, month, year = text.split('/')
            return f"{day}-{month}-{year}"
        return text
    except:
        return ""


def to_number(text: str) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except:
        return 0.0


def extract_baroda_data(file_bytes, password=None):
    """
    Bank of Baroda statement extractor using strict column rules
    Columns: DATE | NARRATION | CHQ.NO. | WITHDRAWAL(DR) | DEPOSIT(CR) | BALANCE(AED)
    """
    rows = []

    with pdfplumber.open(BytesIO(file_bytes), password=password) as pdf:
        print(f"Processing {len(pdf.pages)} pages...")
        
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"Processing page {page_num}...")
            
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

            # Use strict column boundaries based on the Bank of Baroda screenshot layout
            # Adjusted to match exact positions shown in the statement
            date_range = (0, 80)            # Date column (narrow, leftmost)
            narration_range = (80, 420)     # Narration column (wide middle section)
            ref_range = (420, 480)          # CHQ.NO./Reference column (narrow)
            withdrawal_range = (480, 560)   # WITHDRAWAL(DR) column 
            deposit_range = (560, 640)      # DEPOSIT(CR) column
            balance_range = (640, 9999)     # BALANCE(AED) column (ignore)

            def get_column(x_pos):
                """Determine which column an x position belongs to"""
                if date_range[0] <= x_pos < date_range[1]:
                    return "date"
                elif narration_range[0] <= x_pos < narration_range[1]:
                    return "narration"
                elif ref_range[0] <= x_pos < ref_range[1]:
                    return "reference"
                elif withdrawal_range[0] <= x_pos < withdrawal_range[1]:
                    return "withdrawal"
                elif deposit_range[0] <= x_pos < deposit_range[1]:
                    return "deposit"
                else:
                    return "balance"  # Ignore balance column

            # Find the first transaction line to determine where data starts
            data_start_y = None
            date_found_count = 0
            
            # Look for date patterns more broadly
            for top, word_list in sorted_lines:
                for w in word_list:
                    if re.match(r'^\d{2}/\d{2}/\d{4}', w["text"]):
                        if not data_start_y:
                            data_start_y = top - 10  # Start closer to the first transaction
                        date_found_count += 1
                        print(f"Page {page_num}: Found date '{w['text']}' at y={top}")
                        break
            
            print(f"Page {page_num}: Found {date_found_count} date patterns, data_start_y={data_start_y}")
            
            # If no date found, use a more aggressive approach
            if not data_start_y:
                # Look for any line that might contain transaction data or amounts
                for top, word_list in sorted_lines:
                    line_text = " ".join(w["text"] for w in word_list)
                    # Look for common transaction keywords or amount patterns
                    if (any(keyword in line_text.upper() for keyword in [
                        'CLEARING', 'COMMERCE', 'TRANSFER', 'WITHDRAWAL', 'DEPOSIT', 
                        'PAYMENT', 'INST', 'OUTWARD', 'INWARD', 'CHEQUE', 'CASH'
                    ]) or re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b", line_text)):
                        data_start_y = top - 10
                        print(f"Page {page_num}: Found transaction indicator at y={top}, line: {line_text[:50]}...")
                        break
            
            # Final fallback - use a very low threshold to capture all possible transactions
            if not data_start_y:
                data_start_y = 100  # Very low threshold to capture everything
                print(f"Page {page_num}: Using fallback data_start_y={data_start_y}")

            # Process each line to find transactions
            page_transactions = 0
            processed_lines = 0
            
            for top, word_list in sorted_lines:
                # Skip header area but process all data areas
                if top < data_start_y:
                    continue
                
                processed_lines += 1

                # Build column data for this line using strict column boundaries
                line_data = {
                    "date": "",
                    "narration": "",
                    "reference": "",
                    "withdrawal": "",
                    "deposit": "",
                    "balance": ""
                }

                for w in sorted(word_list, key=lambda w: w["x0"]):
                    text = w["text"].strip()
                    if not text or is_arabic(text):
                        continue
                    
                    x_pos = float(w["x0"])
                    col = get_column(x_pos)
                    
                    # Debug: Show where amounts are being placed
                    if re.search(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b|\b\d+(?:\.\d{2})?\b", text):
                        print(f"Page {page_num}: Amount '{text}' at x={x_pos} -> column '{col}'")
                    
                    if col != "balance":  # Ignore balance column completely
                        if line_data[col]:
                            line_data[col] += " " + text
                        else:
                            line_data[col] = text

                # Check if this line contains a date (DD/MM/YYYY format)
                date_text = line_data["date"].strip()
                if re.match(r"^\d{2}/\d{2}/\d{4}", date_text):
                    # Extract description from narration column (single line)
                    description = clean_text(line_data["narration"])
                    
                    print(f"Page {page_num}: Found transaction - Date: {date_text}, Description: {description[:30]}...")
                    print(f"Page {page_num}: Column data - Withdrawal: '{line_data['withdrawal']}', Deposit: '{line_data['deposit']}', Reference: '{line_data['reference']}'")
                    
                    # Skip if no meaningful description (be less strict)
                    if not description or len(description) < 2:
                        print(f"Page {page_num}: Skipping transaction - description too short: '{description}'")
                        continue
                    
                    # Extract reference number from CHQ.NO. column
                    reference = clean_text(line_data["reference"])
                    
                    # Extract amounts using strict column logic with comprehensive number detection
                    withdrawal_amount = 0.0
                    deposit_amount = 0.0
                    
                    # Process withdrawal column - extract ALL number formats
                    withdrawal_text = line_data["withdrawal"].strip()
                    if withdrawal_text:
                        # Comprehensive regex to capture formats like: 6,264.10, 16,296.00, 80.02, 7,268.00, 1234, 12.34
                        withdrawal_matches = re.findall(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)\b", withdrawal_text)
                        if withdrawal_matches:
                            # Take the first valid amount found
                            withdrawal_amount = to_number(withdrawal_matches[0])
                            print(f"Page {page_num}: Withdrawal amount found: '{withdrawal_matches[0]}' -> {withdrawal_amount}")
                    
                    # Process deposit column - extract ALL number formats
                    deposit_text = line_data["deposit"].strip()
                    if deposit_text:
                        # Comprehensive regex to capture formats like: 6,264.10, 16,296.00, 80.02, 7,268.00, 1234, 12.34
                        deposit_matches = re.findall(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)\b", deposit_text)
                        if deposit_matches:
                            # Take the first valid amount found
                            deposit_amount = to_number(deposit_matches[0])
                            print(f"Page {page_num}: Deposit amount found: '{deposit_matches[0]}' -> {deposit_amount}")
                    
                    print(f"Page {page_num}: Amounts - Withdrawal: {withdrawal_amount}, Deposit: {deposit_amount}")
                    
                    # Create transaction record using strict column mapping
                    transaction = {
                        "Date": parse_date(date_text),
                        "Withdrawals": withdrawal_amount,  # WITHDRAWAL(DR) column
                        "Deposits": deposit_amount,        # DEPOSIT(CR) column
                        "Payee": "",
                        "Description": description,        # NARRATION column
                        "Reference Number": reference      # CHQ.NO. column
                    }
                    
                    # Only add if we have a valid date (amounts can be zero for some transactions)
                    if transaction["Date"]:
                        rows.append(transaction)
                        page_transactions += 1
                        print(f"Page {page_num}: Added transaction #{page_transactions}")
                    else:
                        print(f"Page {page_num}: Skipping transaction - no valid date")
            
            print(f"Page {page_num}: Processed {processed_lines} lines, found {page_transactions} transactions")

    print(f"Total transactions found: {len(rows)}")
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Remove any balance-related entries and transactions with no amounts
    if not df.empty:
        df = df[~df['Description'].str.contains('balance|opening|closing', case=False, na=False)]
        # Only remove transactions that have absolutely no amounts (both are 0)
        df = df[~((df['Withdrawals'] == 0) & (df['Deposits'] == 0))]
    
    # Ensure all required columns exist
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            df[col] = "" if col in ["Payee", "Description", "Reference Number"] else 0.0

    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]