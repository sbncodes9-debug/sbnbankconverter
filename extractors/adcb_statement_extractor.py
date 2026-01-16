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

                        # Extract Bank Reference, Customer Reference, and Description
                        # Columns: 2=Value Date, 3=Bank Ref, 4=Customer Ref, 5=Description
                        bank_ref = ""
                        customer_ref = ""
                        description = ""
                        
                        # Column 3: Bank Reference (alphanumeric like PHUB48349, CHRG49006, etc.)
                        if len(row) > 3 and row[3]:
                            bank_ref_text = str(row[3]).strip()
                            # Skip if it's a date
                            if not re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$", bank_ref_text):
                                bank_ref = bank_ref_text
                        
                        # Column 4: Customer Reference (numeric like 2025052901, 228111, etc.)
                        if len(row) > 4 and row[4]:
                            customer_ref_text = str(row[4]).strip()
                            # Skip if it's a date
                            if not re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$", customer_ref_text):
                                customer_ref = customer_ref_text
                        
                        # Column 5: Description
                        if len(row) > 5 and row[5]:
                            description = str(row[5]).strip()
                        
                        # Combine references - prefer Bank Reference, fallback to Customer Reference
                        if bank_ref and customer_ref:
                            # If both exist, use Bank Reference and add Customer Reference if it's different
                            ref = bank_ref
                            # Only add customer ref if it's not already in bank ref
                            if customer_ref not in bank_ref and re.match(r'^\d+$', customer_ref):
                                ref = f"{bank_ref} {customer_ref}"
                        elif bank_ref:
                            ref = bank_ref
                        elif customer_ref:
                            ref = customer_ref
                        else:
                            ref = ""

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


def extract_adcb3_format(file_bytes):
    """Extract ADCB3 format (Account Statement with Posting Date, Value Date, Description, Ref/Cheque No, Debit, Credit, Balance)"""
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Use text extraction with column positions
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            i = 0
            
            while i < len(lines):
                line = lines[i]
                line_stripped = line.strip()
                
                # Skip empty lines and headers
                if not line_stripped:
                    i += 1
                    continue
                if any(header in line_stripped.upper() for header in ["POSTING DATE", "VALUE DATE", "DESCRIPTION", "DEBIT AMOUNT", "CREDIT AMOUNT", "REF/CHEQUE"]):
                    i += 1
                    continue
                
                # Look for lines starting with date pattern (dd/mm/yyyy)
                date_match = re.match(r'^(\d{2}/\d{2}/\d{4})', line_stripped)
                if not date_match:
                    i += 1
                    continue
                
                posting_date_str = date_match.group(1)
                date = parse_date_format1(posting_date_str)
                if not date:
                    i += 1
                    continue
                
                # Remove the posting date from the line
                rest_of_line = line_stripped[10:].strip()
                
                # Look for value date (second date)
                value_date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', rest_of_line)
                if value_date_match:
                    rest_of_line = value_date_match.group(2).strip()
                
                # Collect multi-line description
                # Check if next lines are continuation (don't start with date)
                full_line = rest_of_line
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    # Stop if next line starts with a date (new transaction)
                    if re.match(r'^\d{2}/\d{2}/\d{4}', next_line):
                        break
                    # Stop if next line is empty or a header
                    if not next_line or any(header in next_line.upper() for header in ["POSTING DATE", "VALUE DATE", "DESCRIPTION"]):
                        break
                    # Stop if next line looks like a footer or page number
                    if re.match(r'^Page \d+', next_line, re.I) or "Statement" in next_line:
                        break
                    # Add continuation line
                    full_line += " " + next_line
                    j += 1
                
                # Update index to skip processed continuation lines
                i = j
                
                # Find all amounts in the combined line (format: X,XXX.XX or XXX.XX)
                amounts = re.findall(r'\b\d{1,3}(?:,\d{3})*\.\d{2}\b', full_line)
                
                if len(amounts) < 2:
                    continue
                
                # Last 3 amounts are: Debit, Credit, Balance
                # We need Debit and Credit
                debit_str = amounts[-3] if len(amounts) >= 3 else "0.00"
                credit_str = amounts[-2] if len(amounts) >= 2 else "0.00"
                balance_str = amounts[-1] if len(amounts) >= 1 else "0.00"
                
                debit = to_number(debit_str)
                credit = to_number(credit_str)
                
                # Skip if both amounts are zero
                if debit == 0 and credit == 0:
                    continue
                
                # Extract description and reference
                # Remove all amounts from the line to get description + reference
                desc_and_ref = full_line
                for amt in amounts:
                    desc_and_ref = desc_and_ref.replace(amt, ' ')
                
                # Clean up spaces
                desc_and_ref = re.sub(r'\s+', ' ', desc_and_ref).strip()
                
                # Extract reference number - look for patterns with priority:
                # Priority 1: Numbers with # (e.g., 5355546#729) - most reliable
                # Priority 2: Long digit sequences (10+ digits) that appear AFTER the first word
                # Priority 3: Alphanumeric codes (letters + numbers)
                
                ref = ""
                description = desc_and_ref
                
                # Pattern 1: Look for number with # (e.g., 5355546#729) - HIGHEST PRIORITY
                ref_match = re.search(r'\b(\d+#\d+)\b', desc_and_ref)
                if ref_match:
                    ref = ref_match.group(1)
                    description = desc_and_ref.replace(ref, ' ')
                else:
                    # Pattern 2: Look for long digit sequences (10+ digits)
                    # But skip the first long number (likely transaction ID in description)
                    all_long_numbers = re.findall(r'\b(\d{10,})\b', desc_and_ref)
                    if len(all_long_numbers) > 1:
                        # Use the LAST long number as reference (more likely to be ref number)
                        ref = all_long_numbers[-1]
                        description = desc_and_ref.replace(ref, ' ')
                    elif len(all_long_numbers) == 1:
                        # Only one long number - check if it's at the beginning (transaction ID) or later (ref)
                        # If it appears after the first 20 characters, likely a reference
                        ref_pos = desc_and_ref.find(all_long_numbers[0])
                        if ref_pos > 20:
                            ref = all_long_numbers[0]
                            description = desc_and_ref.replace(ref, ' ')
                        # Otherwise, leave it in description (it's a transaction ID)
                    
                    # Pattern 3: Look for alphanumeric patterns only if no long numbers found
                    if not ref:
                        ref_match = re.search(r'\b([A-Z]{2,}[0-9]{5,})\b', desc_and_ref)
                        if ref_match:
                            ref = ref_match.group(1)
                            description = desc_and_ref.replace(ref, ' ')
                
                # Final cleanup of description
                description = re.sub(r'\s+', ' ', description).strip()
                
                if not description:
                    continue
                
                rows.append({
                    "Date": date,
                    "Withdrawals": debit if debit > 0 else "",
                    "Deposits": credit if credit > 0 else "",
                    "Payee": "",
                    "Description": description,
                    "Reference Number": ref
                })

    return rows


def extract_adcb4_format(file_bytes):
    """Extract ADCB4 format (Account Statement with Posting Date+Time, table-based with proper column mapping)"""
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            if not tables:
                continue

            for table in tables:
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 6:
                        continue

                    # Skip header rows
                    if any(header in str(row[0] or "").upper() for header in ["POSTING DATE", "VALUE DATE", "DESCRIPTION", "DEBIT", "CREDIT", "REF/CHEQUE"]):
                        continue
                    
                    # Skip empty rows
                    if not any(cell and str(cell).strip() for cell in row):
                        continue

                    try:
                        # Expected columns: Posting Date | Value Date | Description | Ref/Cheque No | Debit Amount | Credit Amount | Balance
                        # Column indices:    0           | 1          | 2           | 3            | 4           | 5             | 6
                        
                        posting_date_str = str(row[0]).strip() if row[0] else ""
                        
                        # Parse posting date - may include timestamp (dd/mm/yyyy HH-MM-SS)
                        # Extract just the date part
                        date_match = re.match(r'(\d{2}/\d{2}/\d{4})', posting_date_str)
                        if not date_match:
                            continue
                        
                        date = parse_date_format1(date_match.group(1))
                        if not date:
                            continue

                        # Column 2: Description
                        description = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                        
                        # Column 3: Ref/Cheque No
                        ref = str(row[3]).strip() if len(row) > 3 and row[3] else ""
                        
                        # Column 4: Debit Amount (Withdrawals)
                        debit = 0.0
                        if len(row) > 4 and row[4] and str(row[4]).strip():
                            debit_str = str(row[4]).strip()
                            debit_str = re.sub(r'[^\d,.]', '', debit_str)
                            if debit_str:
                                debit = to_number(debit_str)
                        
                        # Column 5: Credit Amount (Deposits)
                        credit = 0.0
                        if len(row) > 5 and row[5] and str(row[5]).strip():
                            credit_str = str(row[5]).strip()
                            credit_str = re.sub(r'[^\d,.]', '', credit_str)
                            if credit_str:
                                credit = to_number(credit_str)

                        # Skip rows with no amounts
                        if debit == 0 and credit == 0:
                            continue
                        
                        # Skip rows with no description
                        if not description:
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
                        print(f"Error processing ADCB4 row {row_idx}: {e}")
                        continue

    return rows


def detect_adcb_format(file_bytes):
    """Detect which ADCB format is being used"""
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
            first_page_upper = first_page_text.upper()
            
            # Check for ADCB4 format FIRST (Account Statement with Posting Date+Time)
            # Look for date with timestamp pattern (dd/mm/yyyy HH-MM-SS or HH:MM:SS)
            if re.search(r'\d{2}/\d{2}/\d{4}\s+\d{2}[-:]\d{2}[-:]\d{2}', first_page_text):
                if "POSTING DATE" in first_page_upper or "VALUE DATE" in first_page_upper:
                    print("Detected ADCB4 format: Account Statement with Posting Date+Time found")
                    return "adcb4"
            
            # Check for ADCB3 format (Account Statement with Posting Date, Value Date columns)
            # This must come before ADCB1 check since both use dd/mm/yyyy dates
            # ADCB3 has specific English headers: "Posting Date", "Value Date", "Debit Amount", "Credit Amount"
            if ("POSTING DATE" in first_page_upper and "VALUE DATE" in first_page_upper) or \
               ("POSTING DATE" in first_page_upper and "REF/CHEQUE" in first_page_upper) or \
               ("POSTING DATE" in first_page_upper and "DEBIT AMOUNT" in first_page_upper and "CREDIT AMOUNT" in first_page_upper):
                print("Detected ADCB3 format: Account Statement with Posting Date/Value Date found")
                return "adcb3"
            
            # Check for ADCB2 format (table structure with Sr No and specific headers)
            tables = pdf.pages[0].extract_tables() if pdf.pages else []
            if tables:
                # Look for table headers that indicate ADCB2 format
                for table in tables:
                    for row in table:
                        if row and any(header in str(row).upper() for header in ["SR NO", "SR.", "BANK REFERENCE", "CUSTOMER REFERENCE"]):
                            print("Detected ADCB2 format: Table structure with Sr No found")
                            return "adcb2"
            
            # Also check text for ADCB2 indicators
            if any(indicator in first_page_upper for indicator in ["SR NO", "BANK REFERENCE NO", "CUSTOMER REFERENCE NO", "RUNNING BALANCE"]):
                print("Detected ADCB2 format: Table headers found in text")
                return "adcb2"
            
            # Check for ADCB1 format (dd/mm/yyyy dates and Arabic layout WITHOUT Posting Date header)
            # ADCB1 typically has Arabic text and simpler column structure
            if re.search(r"\d{2}/\d{2}/\d{4}", first_page_text) and "POSTING DATE" not in first_page_upper:
                # Additional check: ADCB1 often has Arabic text or simpler headers
                if any(arabic_indicator in first_page_text for arabic_indicator in ["التاريخ", "التفاصيل", "الرصيد", "كشف الحساب"]) or \
                   ("Statement of Account" in first_page_text and "POSTING DATE" not in first_page_upper):
                    print("Detected ADCB1 format: dd/mm/yyyy dates with Arabic layout found")
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
    Unified ADCB Statement extractor that handles all five formats
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
    elif format_type == "adcb3":
        rows = extract_adcb3_format(file_bytes)
    elif format_type == "adcb4":
        rows = extract_adcb4_format(file_bytes)
    else:  # current format
        rows = extract_adcb_current_format(file_bytes)
    
    # If no results, try other formats as fallback
    if not rows:
        print(f"No results with {format_type} format, trying other formats...")
        
        if format_type != "adcb4":
            rows = extract_adcb4_format(file_bytes)
        
        if not rows and format_type != "adcb3":
            rows = extract_adcb3_format(file_bytes)
        
        if not rows and format_type != "adcb1":
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