import pdfplumber
import pandas as pd
import re
from io import BytesIO
from dateutil.parser import parse as parse_date

DATE_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"      # 01/12/2024
    r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}\b|"   # 01 Jan 2024
    r"\b\d{2}[A-Z]{3}\d{2}\b|"                 # 02NOV25
    r"\b\d{2}-\d{2}-\d{4}\b|"                  # 02-01-2024 (FAB format)
    r"\b\d{2}/\d{2}/\d{4}\b"                   # 02/01/2024 (FAB format)
)

AMOUNT_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d{2})")

IGNORE_WORDS = (
    "balance", "opening", "closing", "statement",
    "page", "iban", "account", "summary"
)

def clean_text(t):
    t = re.sub(r"[\u0600-\u06FF]", " ", t)   # remove Arabic
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def parse_amount(val):
    val = val.replace(",", "")
    try:
        return float(val)
    except:
        return None

def normalize_date(d):
    try:
        return parse_date(d, dayfirst=True).strftime("%d-%m-%Y")
    except:
        return ""

def is_fab_format(line):
    """Check if line matches FAB bank statement format"""
    # Check for DD/MM/YYYY DD/MM/YYYY or DD-MM-YYYY DD-MM-YYYY format
    fab_pattern1 = r'^\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}'
    fab_pattern2 = r'^\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}'
    return bool(re.match(fab_pattern1, line.strip()) or re.match(fab_pattern2, line.strip()))

def is_fab_tabular_format(line):
    """Check if line matches FAB tabular format (Transaction Date | Payment Date | Narrative | Bank Ref | Channel Ref | Debit | Credit | Balance)"""
    # Look for pattern: DD-MM-YYYY DD-MM-YYYY [text] FT[code] [text] [amount] [amount] [amount]
    tabular_pattern = r'^\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}\s+.*FT\w+.*\d+\.\d{2}.*\d+\.\d{2}.*\d+\.\d{2}'
    return bool(re.search(tabular_pattern, line.strip()))

def is_standard_tabular_format(line):
    """Check if line matches standard tabular format (Posting Date | Value Date | Description | Ref/Cheque No | Debit Amount | Credit Amount | Balance)"""
    # Look for pattern: DD/MM/YYYY DD/MM/YYYY [description] [ref] [amount] [amount] [amount]
    # This format has posting date, value date, description, reference, debit, credit, balance
    standard_pattern = r'^\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}\s+.*\d+\.\d{2}.*\d+\.\d{2}.*\d+\.\d{2}'
    return bool(re.search(standard_pattern, line.strip()))

def extract_standard_tabular_transaction(line):
    """Extract transaction data from standard tabular format line"""
    # Pattern: DD/MM/YYYY DD/MM/YYYY Description Ref/ChequeNo DebitAmount CreditAmount Balance
    date_pattern = r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})'
    date_match = re.match(date_pattern, line.strip())
    
    if not date_match:
        return None
    
    posting_date = date_match.group(1)  # Use posting date instead of value date
    remaining_line = line[date_match.end():].strip()
    
    # Find all amounts (debit, credit, balance - last 3 amounts)
    amount_pattern = r'(\d{1,3}(?:,\d{3})*\.\d{2})'
    amounts = re.findall(amount_pattern, remaining_line)
    
    debit = ""
    credit = ""
    
    # Last 3 amounts should be: debit, credit, balance
    if len(amounts) >= 3:
        try:
            potential_debit = parse_amount(amounts[-3])
            potential_credit = parse_amount(amounts[-2])
            
            # Assign non-zero amounts (debit = withdrawal, credit = deposit)
            if potential_debit and potential_debit > 0:
                debit = potential_debit
            if potential_credit and potential_credit > 0:
                credit = potential_credit
                
        except (ValueError, IndexError):
            pass
    
    # Extract reference and description
    # Remove all amounts first to work with clean text
    text_without_amounts = remaining_line
    for amount in amounts:
        text_without_amounts = text_without_amounts.replace(amount, " ").strip()
    
    # For standard tabular format, the reference is typically positioned right before the amounts
    # Split the text and look for the reference in the expected position
    parts = re.split(r'\s+', text_without_amounts)
    
    # Find reference number - look for specific patterns that are likely to be references
    reference = ""
    
    # More specific patterns for actual reference numbers (not description text)
    ref_patterns = [
        r'\b\d{11,}\b',             # Very long numeric codes (11+ digits)
        r'\bPHUB\d{8,}\b',          # PHUB followed by 8+ digits
        r'\b\d{10}\b',              # Exactly 10 digits
        r'\b[A-Z]{2}\d{8,}\b'       # 2 letters followed by 8+ digits
    ]
    
    # Look for reference patterns in the text
    for pattern in ref_patterns:
        matches = re.findall(pattern, text_without_amounts)
        if matches:
            # Take the first match that looks like a proper reference
            reference = matches[0]
            break
    
    # If no specific pattern found, look for the last standalone alphanumeric code
    # that's not part of a descriptive phrase
    if not reference:
        # Look for standalone codes that are likely references
        standalone_codes = re.findall(r'\b[A-Z0-9]{8,}\b', text_without_amounts)
        if standalone_codes:
            # Filter out codes that are clearly part of descriptions
            for code in reversed(standalone_codes):  # Check from end to start
                # Skip codes that are clearly part of descriptions
                if not any(desc_word in code.lower() for desc_word in ['enterprises', 'trading', 'general', 'company']):
                    reference = code
                    break
    
    # Extract description by removing reference
    description = text_without_amounts
    if reference:
        description = description.replace(reference, " ").strip()
    
    # Clean up the description
    description = re.sub(r'\s+', ' ', description).strip()
    description = clean_text(description)
    
    return {
        "Date": normalize_date(posting_date),
        "Withdrawals": debit if debit else "",
        "Deposits": credit if credit else "",
        "Payee": "",
        "Description": description.strip(),
        "Reference Number": reference
    }

def extract_fab_tabular_transaction(line):
    """Extract transaction data from FAB tabular format line"""
    # Pattern: DD-MM-YYYY DD-MM-YYYY Narrative BankRef ChannelRef Debit Credit Balance
    date_pattern = r'^(\d{2}-\d{2}-\d{4})\s+(\d{2}-\d{2}-\d{4})'
    date_match = re.match(date_pattern, line.strip())
    
    if not date_match:
        return None
    
    transaction_date = date_match.group(1)
    remaining_line = line[date_match.end():].strip()
    
    # Find all amounts (debit, credit, balance - last 3 amounts)
    amount_pattern = r'(\d{1,3}(?:,\d{3})*\.\d{2})'
    amounts = re.findall(amount_pattern, remaining_line)
    
    debit = ""
    credit = ""
    
    # Last 3 amounts should be: debit, credit, balance
    if len(amounts) >= 3:
        try:
            potential_debit = parse_amount(amounts[-3])
            potential_credit = parse_amount(amounts[-2])
            
            # Assign non-zero amounts (debit = withdrawal, credit = deposit)
            if potential_debit and potential_debit > 0:
                debit = potential_debit
            if potential_credit and potential_credit > 0:
                credit = potential_credit
                
        except (ValueError, IndexError):
            pass
    
    # Extract references
    # Remove all amounts first to work with clean text
    text_without_amounts = remaining_line
    for amount in amounts:
        text_without_amounts = text_without_amounts.replace(amount, " ").strip()
    
    # Find bank reference (FT codes)
    bank_reference = ""
    ft_pattern = r'FT\w+'
    ft_matches = re.findall(ft_pattern, text_without_amounts)
    if ft_matches:
        bank_reference = ft_matches[0]  # Take first FT code as bank reference
    
    # Find channel reference (C codes or other alphanumeric codes)
    channel_reference = ""
    channel_pattern = r'C\w+|\w+\d+\w*'
    channel_matches = re.findall(channel_pattern, text_without_amounts)
    # Filter out the FT code we already found
    channel_matches = [ref for ref in channel_matches if not ref.startswith('FT')]
    if channel_matches:
        channel_reference = channel_matches[0]
    
    # Combine references
    all_references = []
    if bank_reference:
        all_references.append(bank_reference)
    if channel_reference:
        all_references.append(channel_reference)
    
    reference = ' '.join(all_references)
    
    # Extract narrative/description by removing references
    description = text_without_amounts
    if bank_reference:
        description = description.replace(bank_reference, " ").strip()
    if channel_reference:
        description = description.replace(channel_reference, " ").strip()
    
    # Clean up the description
    description = re.sub(r'\s+', ' ', description).strip()
    description = clean_text(description)
    
    return {
        "Date": normalize_date(transaction_date),
        "Withdrawals": debit if debit else "",
        "Deposits": credit if credit else "",
        "Payee": "",
        "Description": description.strip(),
        "Reference Number": reference
    }

def extract_fab_transaction(line):
    """Extract transaction data from FAB format line"""
    # Pattern: DD/MM/YYYY DD/MM/YYYY CustomerRef BankRef Description Deposit Withdrawal Balance
    date_pattern = r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})'
    date_match = re.match(date_pattern, line.strip())
    
    if not date_match:
        # Try DD-MM-YYYY format as well
        date_pattern = r'^(\d{2}-\d{2}-\d{4})\s+(\d{2}-\d{2}-\d{4})'
        date_match = re.match(date_pattern, line.strip())
        if not date_match:
            return None
    
    transaction_date = date_match.group(1)
    remaining_line = line[date_match.end():].strip()
    
    # Find all amounts at the end of the line (deposit, withdrawal, balance)
    amount_pattern = r'(\d{1,3}(?:,\d{3})*\.\d{2})'
    amounts = re.findall(amount_pattern, remaining_line)
    
    deposit = ""
    withdrawal = ""
    
    # FAB format: CustomerRef BankRef Description Deposit Withdrawal Balance
    # Last 3 amounts should be: deposit, withdrawal, balance
    if len(amounts) >= 3:
        try:
            potential_deposit = parse_amount(amounts[-3])
            potential_withdrawal = parse_amount(amounts[-2])
            
            # Assign non-zero amounts
            if potential_deposit and potential_deposit > 0:
                deposit = potential_deposit
            if potential_withdrawal and potential_withdrawal > 0:
                withdrawal = potential_withdrawal
                
        except (ValueError, IndexError):
            pass
    
    # Extract references and description
    # Remove all amounts first to work with clean text
    text_without_amounts = remaining_line
    for amount in amounts:
        text_without_amounts = text_without_amounts.replace(amount, " ").strip()
    
    # Split by multiple spaces to get fields
    parts = re.split(r'\s{2,}', text_without_amounts)
    
    # Find bank reference (FT codes)
    bank_reference = ""
    customer_reference = ""
    
    # Look for FT codes and other references
    ft_pattern = r'FT\w+'
    ft_matches = re.findall(ft_pattern, text_without_amounts)
    if ft_matches:
        bank_reference = ft_matches[0]  # Take first FT code as bank reference
    
    # Look for customer reference (usually numeric)
    cust_ref_pattern = r'\b\d{4,}\b'
    cust_matches = re.findall(cust_ref_pattern, text_without_amounts)
    if cust_matches:
        customer_reference = cust_matches[0]  # Take first numeric code as customer reference
    
    # Combine references
    all_references = []
    if customer_reference:
        all_references.append(customer_reference)
    if bank_reference:
        all_references.append(bank_reference)
    
    reference = ' '.join(all_references)
    
    # Extract description by removing references
    description = text_without_amounts
    if customer_reference:
        description = description.replace(customer_reference, " ").strip()
    if bank_reference:
        description = description.replace(bank_reference, " ").strip()
    
    # Clean up the description
    description = re.sub(r'\s+', ' ', description).strip()
    description = clean_text(description)
    
    return {
        "Date": normalize_date(transaction_date),
        "Withdrawals": withdrawal if withdrawal else "",
        "Deposits": deposit if deposit else "",
        "Payee": "",
        "Description": description.strip(),
        "Reference Number": reference
    }

def extract_universal_data(pdf_bytes):
    rows = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            i = 0
            
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                
                # Check if this is standard tabular format first (most specific)
                if is_standard_tabular_format(line):
                    # For standard tabular format, we might need to combine multiple lines for full description
                    full_line = line
                    
                    # Look ahead for continuation lines (lines that don't start with dates)
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line:
                            j += 1
                            continue
                        
                        # If next line starts with a date, it's a new transaction
                        if (is_standard_tabular_format(next_line) or 
                            is_fab_tabular_format(next_line) or 
                            is_fab_format(next_line)):
                            break
                        
                        # If next line looks like a continuation (no date at start)
                        if not re.match(r'^\d{2}/\d{2}/\d{4}', next_line):
                            full_line += " " + next_line
                            j += 1
                        else:
                            break
                    
                    standard_transaction = extract_standard_tabular_transaction(full_line)
                    if standard_transaction:
                        rows.append(standard_transaction)
                    
                    i = j
                    continue
                
                # Check if this is FAB tabular format (more specific than original FAB)
                elif is_fab_tabular_format(line):
                    # For FAB tabular format, we might need to combine multiple lines for full description
                    full_line = line
                    
                    # Look ahead for continuation lines (lines that don't start with dates)
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line:
                            j += 1
                            continue
                        
                        # If next line starts with a date, it's a new transaction
                        if is_fab_tabular_format(next_line) or is_fab_format(next_line):
                            break
                        
                        # If next line looks like a continuation (no date at start)
                        if not re.match(r'^\d{2}-\d{2}-\d{4}', next_line):
                            full_line += " " + next_line
                            j += 1
                        else:
                            break
                    
                    fab_transaction = extract_fab_tabular_transaction(full_line)
                    if fab_transaction:
                        rows.append(fab_transaction)
                    
                    i = j
                    continue
                
                # Check if this is FAB format (original format)
                elif is_fab_format(line):
                    # For FAB format, we might need to combine multiple lines for full description
                    full_line = line
                    
                    # Look ahead for continuation lines (lines that don't start with dates)
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line:
                            j += 1
                            continue
                        
                        # If next line starts with a date, it's a new transaction
                        if is_fab_format(next_line) or is_fab_tabular_format(next_line):
                            break
                        
                        # If next line looks like a continuation (no date at start)
                        if not re.match(r'^\d{2}-\d{2}-\d{4}', next_line):
                            full_line += " " + next_line
                            j += 1
                        else:
                            break
                    
                    fab_transaction = extract_fab_transaction(full_line)
                    if fab_transaction:
                        rows.append(fab_transaction)
                    
                    i = j
                    continue
                
                # Original universal extraction logic
                low = line.lower()

                if any(w in low for w in IGNORE_WORDS):
                    i += 1
                    continue

                date_match = DATE_RE.search(line)
                amt_match = AMOUNT_RE.search(line)

                if not date_match or not amt_match:
                    i += 1
                    continue

                date_raw = date_match.group()
                amount_raw = amt_match.group()

                amount = parse_amount(amount_raw)
                if amount is None:
                    i += 1
                    continue

                deposits = ""
                withdrawals = ""

                if amount < 0 or "-" in amount_raw:
                    withdrawals = abs(amount)
                else:
                    deposits = abs(amount)

                desc = line
                desc = desc.replace(date_raw, "")
                desc = desc.replace(amount_raw, "")
                desc = clean_text(desc)

                rows.append({
                    "Date": normalize_date(date_raw),
                    "Withdrawals": withdrawals,
                    "Deposits": deposits,
                    "Payee": "",
                    "Description": desc,
                    "Reference Number": ""
                })
                
                i += 1

    return pd.DataFrame(
        rows,
        columns=[
            "Date", "Withdrawals", "Deposits",
            "Payee", "Description", "Reference Number"
        ]
    )
