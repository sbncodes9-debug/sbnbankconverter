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


def parse_date(text):
    """Convert date from dd/mm/yyyy to dd-mm-yyyy format"""
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    """Convert text to number, handling negative amounts"""
    if not text:
        return 0.0
    
    # Remove commas and any extra spaces
    text = text.replace(",", "").strip()
    try:
        return float(text)
    except:
        return 0.0


def extract_pluto_data(file_bytes, password=None):
    """
    Pluto Bank Statement extractor with text-first approach
    Format: Posting Date | Transaction Date | Type | Merchant | User/Last4 | Amount (AED) | Balance (AED)
    """
    rows = []

    try:
        # Use text extraction as primary method for Pluto statements
        with pdfplumber.open(BytesIO(file_bytes), password=password) as pdf:
            print(f"Processing {len(pdf.pages)} pages...")
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"Processing page {page_num}...")
                text = page.extract_text()
                if not text:
                    print(f"No text found on page {page_num}")
                    continue

                lines = text.split('\n')
                page_transactions = 0
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if not line:
                        i += 1
                        continue
                    
                    # Look for transaction lines starting with date pattern (dd/mm/yyyy)
                    date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', line)
                    if not date_match:
                        i += 1
                        continue
                    
                    posting_date_str = date_match.group(1)
                    rest_of_line = date_match.group(2).strip()
                    
                    # Parse posting date
                    date = parse_date(posting_date_str)
                    if not date:
                        i += 1
                        continue
                    
                    # Skip header lines
                    if 'POSTING' in rest_of_line.upper() or 'TRANSACTION DATE' in rest_of_line.upper():
                        i += 1
                        continue
                    
                    # Check if next line contains T-number and should be combined
                    combined_line = rest_of_line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line starts with T- pattern, combine it
                        if re.match(r'^T-\d+', next_line):
                            combined_line = rest_of_line + " " + next_line
                            i += 1  # Skip the next line since we've processed it
                    
                    # Look for amount patterns - try multiple patterns to be more flexible
                    # But exclude foreign currency amounts (PKR, QAR, USD, etc.)
                    amount_match = None
                    amount_str = ""
                    
                    # First, find all potential amounts
                    all_amounts = re.findall(r'(-?\d{1,3}(?:,\d{3})*\.\d{2})', combined_line)
                    
                    # Filter out foreign currency amounts
                    aed_amounts = []
                    for amt in all_amounts:
                        # Check if this amount is preceded by a currency code
                        amt_pattern = re.escape(amt)
                        # Look for currency codes before the amount (PKR, QAR, USD, EUR, GBP, etc.)
                        currency_pattern = r'[A-Z]{3}' + amt_pattern
                        if not re.search(currency_pattern, combined_line):
                            aed_amounts.append(amt)
                    
                    if not aed_amounts:
                        i += 1
                        continue
                    
                    # Pattern 1: AED Amount followed by balance (transaction amount balance)
                    pattern1 = r'(-?\d{1,3}(?:,\d{3})*\.\d{2})\s+\d{1,3}(?:,\d{3})*\.\d{2}$'
                    match1 = re.search(pattern1, combined_line)
                    
                    # Pattern 2: Just AED amount at the end
                    pattern2 = r'(-?\d{1,3}(?:,\d{3})*\.\d{2})$'
                    match2 = re.search(pattern2, combined_line)
                    
                    # Validate that the matched amount is in our AED amounts list
                    if match1 and match1.group(1) in aed_amounts:
                        amount_match = match1
                        amount_str = match1.group(1)
                    elif match2 and match2.group(1) in aed_amounts:
                        amount_match = match2
                        amount_str = match2.group(1)
                    elif aed_amounts:
                        # Use the first AED amount found (likely the transaction amount)
                        amount_str = aed_amounts[0]
                        amount_match = True  # Just to indicate we found something
                    else:
                        i += 1
                        continue
                    
                    amount_str = amount_match.group(1) if hasattr(amount_match, 'group') else amount_str
                    amount = to_number(amount_str)
                    
                    if amount == 0:
                        i += 1
                        continue
                    
                    # Extract everything before the amount as full description
                    if hasattr(amount_match, 'group'):
                        desc_end = combined_line.rfind(amount_match.group(0))
                        full_description = combined_line[:desc_end].strip() if desc_end > 0 else combined_line
                    else:
                        # For filtered AED amounts case, remove only AED amounts from description
                        full_description = combined_line
                        for amt in aed_amounts:
                            full_description = full_description.replace(amt, " ")
                    
                    full_description = clean_text(full_description)
                    
                    if not full_description:
                        i += 1
                        continue
                    
                    # Extract reference number from Type column content
                    reference = ""
                    # Look for "Card Transaction" followed by T-number, or just "Deposit"
                    if "Card Transaction" in full_description:
                        # Look for T-number anywhere in the description
                        t_match = re.search(r'T-\d+', full_description)
                        if t_match:
                            reference = f"Card Transaction {t_match.group()}"
                        else:
                            reference = "Card Transaction"
                    elif "Deposit" in full_description:
                        reference = "Deposit"
                    
                    # Now clean description: remove dates, reference numbers, and extra text
                    description = full_description
                    if description:
                        # Remove dates (dd/mm/yyyy format)
                        description = re.sub(r'\b\d{2}/\d{2}/\d{4}\b', '', description)
                        # Remove reference numbers (T-xxxxxx format) - AFTER extracting for reference
                        description = re.sub(r'\bT-\d+\b', '', description)
                        # Remove transaction IDs that might appear
                        description = re.sub(r'\b\d{7,}\b', '', description)
                        # Clean up extra spaces
                        description = re.sub(r'\s+', ' ', description).strip()
                        # Remove "Card Transaction" prefix if present
                        description = re.sub(r'^Card Transaction\s*', '', description)
                        # Remove "Deposit" prefix if present
                        description = re.sub(r'^Deposit\s*', '', description)
                    
                    # Skip empty descriptions after cleaning
                    if not description:
                        i += 1
                        continue
                    
                    # Determine deposits vs withdrawals
                    withdrawals = 0.0
                    deposits = 0.0
                    
                    if amount > 0:
                        deposits = amount
                    else:
                        withdrawals = abs(amount)
                    
                    rows.append({
                        "Date": date,
                        "Withdrawals": withdrawals if withdrawals > 0 else "",
                        "Deposits": deposits if deposits > 0 else "",
                        "Payee": "",
                        "Description": description,
                        "Reference Number": reference
                    })
                    page_transactions += 1
                    
                    i += 1
                
                print(f"Found {page_transactions} transactions on page {page_num}")

        # If still no rows and OCR is available, try OCR
        if not rows and OCR_AVAILABLE:
            print("Text extraction failed, trying OCR...")
            full_text = extract_text_hybrid(file_bytes)
            if full_text:
                full_text = clean_ocr_text(full_text)
                print(f"OCR extracted {len(full_text)} characters")
                
                # Process OCR text with multi-line processing
                lines = full_text.split('\n')
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if not line:
                        i += 1
                        continue
                    
                    date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', line)
                    if not date_match:
                        i += 1
                        continue
                    
                    posting_date_str = date_match.group(1)
                    rest_of_line = date_match.group(2).strip()
                    
                    date = parse_date(posting_date_str)
                    if not date:
                        i += 1
                        continue
                    
                    if 'POSTING' in rest_of_line.upper() or 'TRANSACTION DATE' in rest_of_line.upper():
                        i += 1
                        continue
                    
                    # Check if next line contains T-number and should be combined
                    combined_line = rest_of_line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line starts with T- pattern, combine it
                        if re.match(r'^T-\d+', next_line):
                            combined_line = rest_of_line + " " + next_line
                            i += 1  # Skip the next line since we've processed it
                    
                    # Look for amount patterns - more flexible approach but exclude foreign currencies
                    all_amounts = re.findall(r'(-?\d{1,3}(?:,\d{3})*\.\d{2})', combined_line)
                    
                    # Filter out foreign currency amounts
                    aed_amounts = []
                    for amt in all_amounts:
                        # Check if this amount is preceded by a currency code
                        amt_pattern = re.escape(amt)
                        # Look for currency codes before the amount (PKR, QAR, USD, EUR, GBP, etc.)
                        currency_pattern = r'[A-Z]{3}' + amt_pattern
                        if not re.search(currency_pattern, combined_line):
                            aed_amounts.append(amt)
                    
                    if not aed_amounts:
                        i += 1
                        continue
                    
                    # Use the first AED amount as transaction amount (usually the transaction amount, not balance)
                    amount = to_number(aed_amounts[0])
                    
                    if amount == 0:
                        i += 1
                        continue
                    
                    # Extract description and reference
                    full_description = combined_line
                    # Remove only AED amounts from description, keep foreign currency amounts visible
                    for amt in aed_amounts:
                        full_description = full_description.replace(amt, " ")
                    full_description = clean_text(full_description)
                    
                    if not full_description:
                        i += 1
                        continue
                    
                    # Extract reference from Type column content
                    reference = ""
                    if "Card Transaction" in full_description:
                        # Look for T-number anywhere in the description
                        t_match = re.search(r'T-\d+', full_description)
                        if t_match:
                            reference = f"Card Transaction {t_match.group()}"
                        else:
                            reference = "Card Transaction"
                    elif "Deposit" in full_description:
                        reference = "Deposit"
                    
                    # Clean description AFTER extracting reference
                    description = full_description
                    if description:
                        description = re.sub(r'\b\d{2}/\d{2}/\d{4}\b', '', description)
                        description = re.sub(r'\bT-\d+\b', '', description)  # Remove AFTER reference extraction
                        description = re.sub(r'\b\d{7,}\b', '', description)
                        description = re.sub(r'\s+', ' ', description).strip()
                        description = re.sub(r'^Card Transaction\s*', '', description)
                        description = re.sub(r'^Deposit\s*', '', description)
                    
                    if not description:
                        i += 1
                        continue
                    
                    withdrawals = 0.0
                    deposits = 0.0
                    
                    if amount > 0:
                        deposits = amount
                    else:
                        withdrawals = abs(amount)
                    
                    rows.append({
                        "Date": date,
                        "Withdrawals": withdrawals if withdrawals > 0 else "",
                        "Deposits": deposits if deposits > 0 else "",
                        "Payee": "",
                        "Description": description,
                        "Reference Number": reference
                    })
                    
                    i += 1

    except Exception as e:
        print(f"Error in Pluto extraction: {e}")
        return pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits",
            "Payee", "Description", "Reference Number"
        ])

    print(f"Total transactions extracted: {len(rows)}")
    df = pd.DataFrame(rows)
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]