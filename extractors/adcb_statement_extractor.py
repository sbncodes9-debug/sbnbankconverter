import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

# Import OCR helper (comment out if OCR not available)
try:
    from .ocr_helper import extract_text_hybrid, clean_ocr_text
    OCR_AVAILABLE = True
except ImportError:
    print("OCR not available - install pytesseract, Pillow, opencv-python")
    OCR_AVAILABLE = False


def clean_text(s):
    if not s:
        return ""
    s = s.replace("\x00", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_date_format1(text):
    """Parse dd/mm/yyyy format (ADCB1)"""
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except:
        return ""


def parse_date_format2(text):
    """Parse dd-mmm-yyyy format (ADCB2 and current)"""
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        return float(text.replace(",", "").strip())
    except:
        return 0.0


def extract_adcb1_format(file_bytes):
    """Extract ADCB1 format (dd/mm/yyyy, text-based Arabic format)"""
    rows = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().split("\n")
            current = None
            desc_buffer = []
            last_balance = None

            for line in lines:
                line = line.strip()

                # Skip headers and empty lines
                if not line or any(header in line for header in ["Date", "Balance", "الرصيد", "التاريخ", "التفاصيل", "Page"]):
                    continue

                # Start of new transaction (Date at column start)
                if re.match(r"^\d{2}/\d{2}/\d{4}", line):
                    # Save old transaction
                    if current:
                        current["Description"] = " ".join(desc_buffer).strip()
                        if current["Description"] or current["Withdrawals"] or current["Deposits"]:
                            rows.append(current)

                    desc_buffer = []
                    date = parse_date_format1(line[:10])

                    # For Arabic ADCB format, the structure is typically:
                    # Date | Description | Chq/Ref No | Value Date | Debit | Credit | Balance
                    
                    # Find all numbers in the line (amounts and balance)
                    nums = re.findall(r"[\d,]+\.\d{2}", line)
                    
                    debit = 0.0
                    credit = 0.0
                    balance = None
                    
                    # Extract amounts based on position and context
                    if len(nums) >= 3:
                        # Last number is usually balance
                        balance = to_number(nums[-1])
                        
                        # Check if we have debit and credit amounts
                        if len(nums) == 3:
                            # Two amounts + balance: determine which is debit/credit
                            amount1 = to_number(nums[0])
                            amount2 = to_number(nums[1])
                            
                            # Use balance trend to determine debit vs credit
                            if last_balance is not None and balance is not None:
                                if balance < last_balance:
                                    # Balance decreased, so it's a debit
                                    debit = amount1 if amount1 > 0 else amount2
                                else:
                                    # Balance increased, so it's a credit
                                    credit = amount1 if amount1 > 0 else amount2
                            else:
                                # No balance history, check line content for clues
                                if any(keyword in line.upper() for keyword in ["DEPOSIT", "CREDIT", "CR"]):
                                    credit = amount1 if amount1 > 0 else amount2
                                else:
                                    debit = amount1 if amount1 > 0 else amount2
                        
                        elif len(nums) >= 4:
                            # Multiple amounts: typically debit, credit, balance
                            debit = to_number(nums[-3]) if nums[-3] else 0.0
                            credit = to_number(nums[-2]) if nums[-2] else 0.0
                            balance = to_number(nums[-1])
                    
                    elif len(nums) == 2:
                        # Amount + Balance
                        amount = to_number(nums[0])
                        balance = to_number(nums[1])
                        
                        # Determine if it's debit or credit based on balance change
                        if last_balance is not None and balance is not None:
                            if balance < last_balance:
                                debit = amount
                            else:
                                credit = amount
                        else:
                            # Default to debit if no balance history
                            debit = amount
                    
                    elif len(nums) == 1:
                        # Only one number - could be amount or balance
                        amount = to_number(nums[0])
                        if amount > 10000:  # Likely a balance
                            balance = amount
                        else:  # Likely a transaction amount
                            debit = amount

                    last_balance = balance

                    current = {
                        "Date": date,
                        "Withdrawals": debit if debit > 0 else "",
                        "Deposits": credit if credit > 0 else "",
                        "Payee": "",
                        "Description": "",
                        "Reference Number": ""
                    }

                    # Extract reference number (look for 6+ digit numbers)
                    ref_matches = re.findall(r"\b\d{6,}\b", line)
                    if ref_matches:
                        # Use the longest reference number found
                        current["Reference Number"] = max(ref_matches, key=len)

                    # Extract description (everything between date and amounts)
                    desc_part = line[10:].strip()  # Remove date
                    
                    # Remove amounts and balance from description
                    for num in nums:
                        desc_part = desc_part.replace(num, " ")
                    
                    # Remove reference numbers from description
                    for ref in ref_matches:
                        desc_part = desc_part.replace(ref, " ")
                    
                    # Clean up description
                    desc_part = re.sub(r'\s+', ' ', desc_part).strip()
                    
                    if desc_part:
                        desc_buffer.append(desc_part)

                else:
                    # Continue collecting description lines
                    if current and line:
                        # Skip lines that look like continuation of amounts or dates
                        if re.search(r"^\d{2}/\d{2}/\d{4}", line):
                            continue
                        if re.search(r"balance|page|الرصيد|صفحة", line, re.I):
                            continue
                        if re.match(r"^[\d\s\.,]+$", line):  # Skip lines with only numbers
                            continue
                        
                        desc_buffer.append(line)

            # Save last transaction
            if current:
                current["Description"] = " ".join(desc_buffer).strip()
                if current["Description"] or current["Withdrawals"] or current["Deposits"]:
                    rows.append(current)

    return rows


def extract_adcb2_format(file_bytes):
    """Extract ADCB2 format (dd-mmm-yyyy, table-based)"""
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            if not tables:
                continue

            for table in tables:
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 6:  # Need at least 6 columns
                        continue

                    # Skip header rows
                    if any(header in str(row[0] or "").upper() for header in ["SR NO", "SR.", "DATE", "DESCRIPTION", "DEBIT", "CREDIT"]):
                        continue
                    
                    # Skip empty rows
                    if not any(cell and str(cell).strip() for cell in row):
                        continue

                    try:
                        # Expected columns: Sr No | Date | Value Date | Bank Ref | Customer Ref | Description | Debit | Credit | Balance
                        sr_no = row[0] if row[0] else ""
                        
                        # Skip if Sr No is not a number
                        if not str(sr_no).strip().isdigit():
                            continue
                        
                        date_str = row[1] if len(row) > 1 else ""
                        
                        # Parse date
                        date = parse_date_format2(date_str) if date_str else ""
                        if not date:
                            continue

                        # Extract description and reference from middle columns
                        desc_parts = []
                        ref = ""
                        
                        # Look at columns 2-5 for references and description
                        for col_idx in range(2, min(6, len(row))):
                            if not row[col_idx] or not str(row[col_idx]).strip():
                                continue
                            
                            col_text = str(row[col_idx]).strip()
                            
                            # Skip value dates (pattern: DD-MMM-YYYY)
                            if re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$", col_text):
                                continue
                            
                            # Extract reference number (bank reference or customer reference)
                            if re.search(r"\d{8,}", col_text) and not ref:
                                # Capture the longest digit sequence as reference
                                matches = re.findall(r"\d{8,}", col_text)
                                if matches:
                                    ref = matches[0]
                            
                            # Add to description if it contains meaningful text
                            if col_text and not re.match(r"^[\d\s\.\-]+$", col_text):
                                desc_parts.append(col_text)
                        
                        description = " ".join(desc_parts)

                        # Extract amounts from the last 3 columns (Debit, Credit, Balance)
                        debit = 0.0
                        credit = 0.0
                        balance = None

                        # Get numeric columns from the end
                        numeric_start = max(6, len(row) - 3)  # Start from column 6 or last 3 columns
                        numeric_cols = row[numeric_start:]
                        
                        if len(numeric_cols) >= 2:
                            # Debit amount
                            if numeric_cols[0] and str(numeric_cols[0]).strip():
                                debit = to_number(str(numeric_cols[0]))
                            
                            # Credit amount
                            if len(numeric_cols) > 1 and numeric_cols[1] and str(numeric_cols[1]).strip():
                                credit = to_number(str(numeric_cols[1]))
                            
                            # Balance (optional)
                            if len(numeric_cols) > 2 and numeric_cols[2] and str(numeric_cols[2]).strip():
                                balance = to_number(str(numeric_cols[2]))

                        # Skip rows with no amounts
                        if debit == 0 and credit == 0:
                            continue

                        rows.append({
                            "Date": date,
                            "Withdrawals": debit if debit > 0 else "",
                            "Deposits": credit if credit > 0 else "",
                            "Payee": "",
                            "Description": clean_text(description),
                            "Reference Number": ref
                        })
                        
                    except Exception as e:
                        print(f"Error processing row {row_idx}: {e}")
                        continue

    return rows


def extract_adcb_current_format(file_bytes):
    """Extract current ADCB format (dd-mmm-yyyy, text-based with OCR)"""
    rows = []

    try:
        # First try normal PDF text extraction
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    full_text += "\n" + txt

        # If normal extraction failed and OCR is available, try OCR
        if (not full_text.strip() or len(full_text.strip()) < 100) and OCR_AVAILABLE:
            print("Normal PDF extraction insufficient, trying OCR...")
            full_text = extract_text_hybrid(file_bytes)
            if full_text:
                full_text = clean_ocr_text(full_text)
                print(f"OCR extracted {len(full_text)} characters")

        if not full_text.strip():
            return []

        # Detect transaction starts
        txn_matches = list(re.finditer(
            r"^\d+\s+\d{2}-[A-Za-z]{3}-\d{4}",
            full_text,
            re.M
        ))

        if not txn_matches:
            return []

        for idx, match in enumerate(txn_matches):
            start = match.start()
            end = txn_matches[idx + 1].start() if idx + 1 < len(txn_matches) else len(full_text)
            block = full_text[start:end]

            try:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                if not lines:
                    continue

                header = lines[0].split()
                if len(header) < 4:
                    continue

                date = parse_date_format2(header[1])
                if not date:
                    continue

                reference_number = header[3]

                description_parts = []
                withdrawals = 0.0
                deposits = 0.0
                amount_found = False

                for line in lines[1:]:
                    lc = line.replace(",", "")

                    m_debit = re.search(r"(\d+\.\d{2})\s*-\s*$", lc)
                    if m_debit:
                        withdrawals = to_number(m_debit.group(1))
                        amount_found = True
                        continue

                    m_credit = re.search(r"^-\s*(\d+\.\d{2})", lc)
                    if m_credit:
                        deposits = to_number(m_credit.group(1))
                        amount_found = True
                        continue

                    if not amount_found:
                        description_parts.append(line)

                description = clean_text(" ".join(description_parts))

                rows.append({
                    "Date": date,
                    "Withdrawals": withdrawals,
                    "Deposits": deposits,
                    "Payee": "",
                    "Description": description,
                    "Reference Number": reference_number
                })

            except Exception:
                continue

    except Exception:
        return []

    return rows


def detect_adcb_format(file_bytes):
    """Detect which ADCB format is being used"""
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
            
            # Check for ADCB2 format FIRST (table structure with Sr No and specific headers)
            tables = pdf.pages[0].extract_tables() if pdf.pages else []
            if tables:
                # Look for table headers that indicate ADCB2 format
                for table in tables:
                    for row in table:
                        if row and any(header in str(row).upper() for header in ["SR NO", "SR.", "BANK REFERENCE", "CUSTOMER REFERENCE"]):
                            print("Detected ADCB2 format: Table structure with Sr No found")
                            return "adcb2"
            
            # Also check text for ADCB2 indicators
            if any(indicator in first_page_text.upper() for indicator in ["SR NO", "BANK REFERENCE NO", "CUSTOMER REFERENCE NO", "RUNNING BALANCE"]):
                print("Detected ADCB2 format: Table headers found in text")
                return "adcb2"
            
            # Check for ADCB1 format (dd/mm/yyyy dates and specific layout)
            if re.search(r"\d{2}/\d{2}/\d{4}", first_page_text) and "Statement of Account" not in first_page_text:
                print("Detected ADCB1 format: dd/mm/yyyy dates found")
                return "adcb1"
            
            # Check for current format (transaction pattern with serial numbers)
            if re.search(r"^\d+\s+\d{2}-[A-Za-z]{3}-\d{4}", first_page_text, re.M):
                print("Detected current format: Serial number pattern found")
                return "current"
            
            # If Statement of Accounts is mentioned, likely ADCB2 or current
            if "Statement of Accounts" in first_page_text:
                print("Detected ADCB2 format: Statement of Accounts title found")
                return "adcb2"
            
            # Default to ADCB2 format (most common)
            print("Defaulting to ADCB2 format")
            return "adcb2"
            
    except Exception as e:
        print(f"Error in format detection: {e}")
        return "adcb2"


def extract_adcb_statement_data(file_bytes):
    """
    Unified ADCB Statement extractor that handles all three formats
    """
    # Detect format
    format_type = detect_adcb_format(file_bytes)
    print(f"Detected ADCB format: {format_type}")
    
    rows = []
    
    # Try the detected format first
    if format_type == "adcb1":
        rows = extract_adcb1_format(file_bytes)
    elif format_type == "adcb2":
        rows = extract_adcb2_format(file_bytes)
    else:  # current format
        rows = extract_adcb_current_format(file_bytes)
    
    # If no results, try other formats as fallback
    if not rows:
        print(f"No results with {format_type} format, trying other formats...")
        
        if format_type != "adcb1":
            rows = extract_adcb1_format(file_bytes)
        
        if not rows and format_type != "adcb2":
            rows = extract_adcb2_format(file_bytes)
        
        if not rows and format_type != "current":
            rows = extract_adcb_current_format(file_bytes)
    
    print(f"Extracted {len(rows)} transactions")
    
    # Convert to DataFrame
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits",
            "Payee", "Description", "Reference Number"
        ])
    
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]