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
    return re.sub(r"\s+", " ", s).strip()


def parse_date(text):
    try:
        # Handle dd-mm-yyyy format
        return datetime.strptime(text.strip(), "%d-%m-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        return float(text.replace(",", "").strip())
    except:
        return 0.0


def extract_emirates_islamic_data(file_bytes):
    """
    Emirates Islamic Bank extractor - uses visual line separators
    Format: Multi-line descriptions above date, separated by horizontal lines
    Transaction Reference as separate column
    """
    rows = []

    try:
        # First try normal PDF text extraction
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # Try table extraction first to get structured data
                tables = page.extract_tables()
                
                if tables:
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 6:
                                continue
                            
                            # Skip header rows
                            first_cell = str(row[0] or "").strip()
                            if any(header in first_cell.upper() for header in [
                                'DATE', 'TRANSACTION', 'NARRATION', 'DEBIT', 'CREDIT', 'BALANCE'
                            ]):
                                continue
                            
                            try:
                                # Extract data from table columns
                                # Assuming columns: Date | Value Date | Description | Transaction Reference | Debit | Credit | Balance
                                date_str = str(row[0] or "").strip()
                                value_date = str(row[1] or "").strip() if len(row) > 1 else ""
                                description = str(row[2] or "").strip() if len(row) > 2 else ""
                                transaction_ref = str(row[3] or "").strip() if len(row) > 3 else ""
                                debit_str = str(row[4] or "").strip() if len(row) > 4 else ""
                                credit_str = str(row[5] or "").strip() if len(row) > 5 else ""
                                
                                # Parse date
                                parsed_date = parse_date(date_str) if date_str else ""
                                if not parsed_date:
                                    continue
                                
                                # Parse amounts
                                debit = to_number(debit_str) if debit_str and debit_str != "-" else 0.0
                                credit = to_number(credit_str) if credit_str and credit_str != "-" else 0.0
                                
                                # Clean description (remove dates and amounts that leaked in)
                                description = clean_description(description)
                                
                                # Add transaction
                                if parsed_date and (description or debit > 0 or credit > 0):
                                    rows.append({
                                        "Date": parsed_date,
                                        "Withdrawals": debit,
                                        "Deposits": credit,
                                        "Payee": "",
                                        "Description": description,
                                        "Reference Number": transaction_ref
                                    })
                                    
                            except Exception as e:
                                continue
                
                # If table extraction didn't work, try text-based with line separators
                if not rows:
                    page_text = page.extract_text()
                    if page_text:
                        rows.extend(extract_from_text_with_separators(page_text))

        # If normal extraction failed and OCR is available, try OCR
        if not rows and OCR_AVAILABLE:
            print("Normal PDF extraction insufficient, trying OCR...")
            all_text = extract_text_hybrid(file_bytes)
            if all_text:
                all_text = clean_ocr_text(all_text)
                print(f"OCR extracted {len(all_text)} characters")
                rows.extend(extract_from_text_with_separators(all_text))

    except Exception as e:
        print(f"Error in Emirates Islamic extraction: {e}")

    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Date', 'Description', 'Withdrawals', 'Deposits'], keep='first')
    
    # Ensure all required columns exist
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            if col in ["Withdrawals", "Deposits"]:
                df[col] = 0.0
            else:
                df[col] = ""
    
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]


def extract_from_text_with_separators(text):
    """
    Extract transactions using visual line separators
    """
    rows = []
    
    # Split by horizontal lines or multiple dashes/underscores
    transaction_blocks = re.split(r'[-_]{3,}|={3,}', text)
    
    for block in transaction_blocks:
        if not block.strip():
            continue
        
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) < 2:
            continue
        
        # Skip header blocks
        if any(header in block.upper() for header in [
            'ACCOUNT STATEMENT', 'TRANSACTION DATE', 'VALUE DATE', 'NARRATION', 
            'TRANSACTION REFERENCE', 'DEBIT', 'CREDIT', 'RUNNING BALANCE',
            'ACCOUNT NUMBER', 'CURRENCY', 'ACCOUNT NAME'
        ]):
            continue
        
        # Find the date line (should contain dd-mm-yyyy pattern)
        date_line_idx = -1
        parsed_date = ""
        
        for i, line in enumerate(lines):
            date_match = re.search(r'\b(\d{2}-\d{2}-\d{4})\b', line)
            if date_match:
                date_line_idx = i
                parsed_date = parse_date(date_match.group(1))
                break
        
        if not parsed_date or date_line_idx == -1:
            continue
        
        # Description is everything before the date line
        description_lines = lines[:date_line_idx]
        description = clean_description(' '.join(description_lines))
        
        # Extract amounts and reference from date line and lines after
        amount_lines = lines[date_line_idx:]
        debit = 0.0
        credit = 0.0
        reference = ""
        
        for line in amount_lines:
            # Extract amounts
            amounts = re.findall(r'\b(\d{1,3}(?:,\d{3})*\.\d{2})\b', line)
            for amount_str in amounts:
                amount = to_number(amount_str)
                if amount > 0:
                    # Determine debit vs credit based on context
                    if any(keyword in line.upper() for keyword in [
                        'DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'RECEIVED', 'INCOMING'
                    ]):
                        if credit == 0.0:
                            credit = amount
                    else:
                        if debit == 0.0:
                            debit = amount
            
            # Extract reference number
            ref_matches = re.findall(r'\b([A-Z0-9]{6,})\b', line)
            if ref_matches and not reference:
                # Skip common words that might match the pattern
                for ref in ref_matches:
                    if ref not in ['BALANCE', 'AMOUNT', 'CREDIT', 'DEBIT']:
                        reference = ref
                        break
        
        # Add transaction
        if parsed_date and (description or debit > 0 or credit > 0):
            rows.append({
                "Date": parsed_date,
                "Withdrawals": debit,
                "Deposits": credit,
                "Payee": "",
                "Description": description,
                "Reference Number": reference
            })
    
    return rows


def clean_description(description):
    """
    Clean description by removing dates, amounts, and common artifacts
    """
    if not description:
        return ""
    
    # Remove dates (dd-mm-yyyy format)
    description = re.sub(r'\b\d{2}-\d{2}-\d{4}\b', '', description)
    
    # Remove amounts (numbers with decimals)
    description = re.sub(r'\b\d{1,3}(?:,\d{3})*\.\d{2}\b', '', description)
    
    # Remove common artifacts
    description = re.sub(r'\b(DEBIT|CREDIT|BALANCE|AMOUNT|TRANSACTION|REFERENCE)\b', '', description, flags=re.IGNORECASE)
    
    # Remove extra whitespace and clean up
    description = re.sub(r'\s+', ' ', description).strip()
    description = re.sub(r'^[\s\-\.\,]+|[\s\-\.\,]+$', '', description)
    
    return description


def finalize_transaction(current_transaction, description_parts):
    """
    Finalize a transaction by combining all collected information
    """
    try:
        date = current_transaction.get('date', '')
        if not date:
            return None
        
        # Combine description parts
        description = clean_text(' '.join(description_parts))
        
        # Get amounts
        debit = current_transaction.get('debit', 0.0)
        credit = current_transaction.get('credit', 0.0)
        
        # Get reference
        reference = current_transaction.get('reference', '')
        
        # If no amounts were found in the structured way, try to extract from description
        if debit == 0.0 and credit == 0.0:
            amounts = re.findall(r'\b(\d{1,3}(?:,\d{3})*\.\d{2})\b', description)
            if amounts:
                amount = to_number(amounts[0])
                # Determine if it's debit or credit based on keywords
                if any(keyword in description.upper() for keyword in ['TRANSFER FROM', 'DEPOSIT', 'CREDIT']):
                    credit = amount
                else:
                    debit = amount
        
        # Extract reference from description if not found
        if not reference:
            ref_matches = re.findall(r'\b([A-Z0-9]{8,})\b', description)
            if ref_matches:
                reference = ref_matches[0]
        
        return {
            "Date": date,
            "Withdrawals": debit,
            "Deposits": credit,
            "Payee": "",
            "Description": description,
            "Reference Number": reference
        }
        
    except Exception as e:
        print(f"Error finalizing transaction: {e}")
        return None