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
    """Convert text to number, handling Cr suffix for credits"""
    if not text:
        return 0.0
    
    # Remove 'Cr' suffix and any extra spaces
    text = text.replace("Cr", "").replace(",", "").strip()
    try:
        return float(text)
    except:
        return 0.0


def is_credit_transaction(amount_text):
    """Check if transaction is a credit (deposit) based on 'Cr' suffix"""
    return "Cr" in str(amount_text)


def extract_rakbank_cc_data(file_bytes):
    """
    RAKBank Credit Card Statement extractor with OCR support
    Format: Date | Transaction Description | Transaction Currency | Transaction Amount | FX Rate | Total Amount(AED)
    """
    rows = []

    try:
        # First try normal PDF text extraction
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Look for transaction lines starting with date pattern (dd/mm/yyyy)
                    date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', line)
                    if not date_match:
                        continue
                    
                    date_str = date_match.group(1)
                    rest_of_line = date_match.group(2).strip()
                    
                    # Parse date
                    date = parse_date(date_str)
                    if not date:
                        continue
                    
                    # Skip header lines and card number lines
                    if any(keyword in rest_of_line.upper() for keyword in [
                        'TRANSACTION', 'DESCRIPTION', 'CURRENCY', 'AMOUNT', 'CARD NO'
                    ]):
                        continue
                    
                    # Look for amount patterns at the end of the line
                    # Pattern: AED amount - total_amount or QAR amount fx_rate total_amount
                    amount_pattern = r'(AED|QAR|USD|EUR|GBP)\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?\s*(?:(\d+\.\d+)\s+)?(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?$'
                    amount_match = re.search(amount_pattern, rest_of_line)
                    
                    if not amount_match:
                        # Try simpler pattern for AED only transactions
                        amount_pattern = r'AED\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?'
                        amount_match = re.search(amount_pattern, rest_of_line)
                        if not amount_match:
                            continue
                        
                        # Extract amount and credit indicator for AED transactions
                        amount_str = amount_match.group(1)
                        is_credit = bool(amount_match.group(2))
                        amount = to_number(amount_str)
                    else:
                        # Handle foreign currency transactions
                        currency = amount_match.group(1)
                        transaction_amount = amount_match.group(2)
                        is_credit_txn = bool(amount_match.group(3))
                        fx_rate = amount_match.group(4)  # May be None for AED transactions
                        total_amount_aed = amount_match.group(5)
                        is_credit_total = bool(amount_match.group(6))
                        
                        # Use the AED total amount for our records
                        amount = to_number(total_amount_aed)
                        is_credit = is_credit_total or is_credit_txn
                    
                    if amount <= 0:
                        continue
                    
                    # Extract description (everything before the currency code)
                    currency_pos = rest_of_line.find('AED')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('QAR')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('USD')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('EUR')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('GBP')
                    
                    description = rest_of_line[:currency_pos].strip() if currency_pos > 0 else rest_of_line
                    description = clean_text(description)
                    
                    # Skip empty descriptions
                    if not description:
                        continue
                    
                    # Set withdrawals or deposits based on Cr suffix
                    withdrawals = 0.0
                    deposits = 0.0
                    
                    if is_credit:
                        deposits = amount
                    else:
                        withdrawals = amount
                    
                    rows.append({
                        "Date": date,
                        "Withdrawals": withdrawals if withdrawals > 0 else "",
                        "Deposits": deposits if deposits > 0 else "",
                        "Payee": "",
                        "Description": description,
                        "Reference Number": ""
                    })

        # If text extraction didn't work and OCR is available, try OCR
        if not rows and OCR_AVAILABLE:
            print("Text extraction failed, trying OCR...")
            full_text = extract_text_hybrid(file_bytes)
            if full_text:
                full_text = clean_ocr_text(full_text)
                print(f"OCR extracted {len(full_text)} characters")
                
                # Process OCR text the same way
                lines = full_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Look for transaction lines starting with date pattern (dd/mm/yyyy)
                    date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+)', line)
                    if not date_match:
                        continue
                    
                    date_str = date_match.group(1)
                    rest_of_line = date_match.group(2).strip()
                    
                    # Parse date
                    date = parse_date(date_str)
                    if not date:
                        continue
                    
                    # Skip header lines and card number lines
                    if any(keyword in rest_of_line.upper() for keyword in [
                        'TRANSACTION', 'DESCRIPTION', 'CURRENCY', 'AMOUNT', 'CARD NO'
                    ]):
                        continue
                    
                    # Look for amount patterns
                    # Handle both AED and foreign currency transactions
                    amount_pattern = r'(AED|QAR|USD|EUR|GBP)\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?\s*(?:(\d+\.\d+)\s+)?(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?$'
                    amount_match = re.search(amount_pattern, rest_of_line)
                    
                    if not amount_match:
                        # Try simpler pattern for AED only
                        amount_pattern = r'AED\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s*(Cr)?'
                        amount_match = re.search(amount_pattern, rest_of_line)
                        if not amount_match:
                            continue
                        
                        amount_str = amount_match.group(1)
                        is_credit = bool(amount_match.group(2))
                        amount = to_number(amount_str)
                    else:
                        # Handle foreign currency transactions
                        currency = amount_match.group(1)
                        transaction_amount = amount_match.group(2)
                        is_credit_txn = bool(amount_match.group(3))
                        fx_rate = amount_match.group(4)
                        total_amount_aed = amount_match.group(5)
                        is_credit_total = bool(amount_match.group(6))
                        
                        # Use the AED total amount
                        amount = to_number(total_amount_aed)
                        is_credit = is_credit_total or is_credit_txn
                    
                    if amount <= 0:
                        continue
                    
                    # Extract description
                    currency_pos = rest_of_line.find('AED')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('QAR')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('USD')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('EUR')
                    if currency_pos == -1:
                        currency_pos = rest_of_line.find('GBP')
                    
                    description = rest_of_line[:currency_pos].strip() if currency_pos > 0 else rest_of_line
                    description = clean_text(description)
                    
                    if not description:
                        continue
                    
                    # Set withdrawals or deposits
                    withdrawals = 0.0
                    deposits = 0.0
                    
                    if is_credit:
                        deposits = amount
                    else:
                        withdrawals = amount
                    
                    rows.append({
                        "Date": date,
                        "Withdrawals": withdrawals if withdrawals > 0 else "",
                        "Deposits": deposits if deposits > 0 else "",
                        "Payee": "",
                        "Description": description,
                        "Reference Number": ""
                    })

    except Exception as e:
        print(f"Error in RAKBank CC extraction: {e}")
        return pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits",
            "Payee", "Description", "Reference Number"
        ])

    df = pd.DataFrame(rows)
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]