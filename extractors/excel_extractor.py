import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def clean_date(text):
    """Convert various date formats to dd-mm-yyyy"""
    if pd.isna(text) or not text:
        return ""
    
    try:
        # If it's already a datetime object
        if isinstance(text, datetime):
            return text.strftime("%d-%m-%Y")
        
        text = str(text).strip()
        
        # Skip if it's clearly not a date
        if text.lower() in ['nan', 'none', '', 'null']:
            return ""
        
        # Handle dd-mm-yyyy (your format) - already in correct format
        if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', text):
            return text
        
        # Handle dd/mm/yyyy, dd.mm.yyyy
        if re.match(r'^\d{1,2}[\/\.]\d{1,2}[\/\.]\d{4}$', text):
            date_obj = pd.to_datetime(text, dayfirst=True)
            return date_obj.strftime("%d-%m-%Y")
        
        # Handle yyyy-mm-dd
        if re.match(r'^\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}$', text):
            date_obj = pd.to_datetime(text)
            return date_obj.strftime("%d-%m-%Y")
        
        # Try pandas auto-detection as last resort
        date_obj = pd.to_datetime(text, dayfirst=True, errors='coerce')
        if pd.notna(date_obj):
            return date_obj.strftime("%d-%m-%Y")
        
        return ""  # Return empty if can't parse
        
    except Exception as e:
        print(f"Date parsing error for '{text}': {e}")
        return ""


def to_number(text):
    """Convert text to number, handling various formats and preserving sign"""
    if pd.isna(text) or not text:
        return 0.0
    
    try:
        # If it's already a number
        if isinstance(text, (int, float)):
            return float(text)  # Keep original sign for amount column format
        
        text = str(text).strip()
        
        # Skip if it's clearly not a number
        if text.lower() in ['nan', 'none', '', 'null', '-']:
            return 0.0
        
        # Remove currency symbols and spaces, but keep signs
        text = re.sub(r'[^\d\.\,\-\+\(\)]', '', text)
        
        if not text:
            return 0.0
        
        # Handle negative signs and brackets
        is_negative = text.startswith('-') or text.startswith('(') or text.endswith(')')
        
        # Remove signs and brackets for processing
        clean_text = re.sub(r'[\-\+\(\)]', '', text)
        
        if not clean_text:
            return 0.0
        
        # Handle comma as thousands separator
        if ',' in clean_text and '.' in clean_text:
            # Format like 1,234.56
            clean_text = clean_text.replace(',', '')
        elif ',' in clean_text and '.' not in clean_text:
            # Could be 1,234 (thousands) or 1,56 (decimal)
            parts = clean_text.split(',')
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Likely decimal: 1,56 -> 1.56
                clean_text = clean_text.replace(',', '.')
            else:
                # Likely thousands: 1,234 -> 1234
                clean_text = clean_text.replace(',', '')
        
        result = float(clean_text) if clean_text else 0.0
        return -result if is_negative else result
        
    except Exception as e:
        print(f"Number parsing error for '{text}': {e}")
        return 0.0


def extract_excel_data(file_bytes, password=None):
    """
    Extract data from Excel or CSV file and convert to standard format
    Supports multiple formats:
    1. Transaction Date | Value Date | Narration | Transaction Reference | Debit | Credit | Running Balance
    2. Date | Description | Amount | Reference (single amount column)
    3. CSV format with various columns including Ref. number, Description, Date, Amount, Balance
    4. Date | Transaction ID | Description | Withdrawal | Deposit | Balance (NEW FORMAT)
    """
    rows = []
    
    try:
        # Try to determine file type and read accordingly
        df = None
        
        # First, try to detect if it's a CSV by attempting to read as CSV
        try:
            # Try reading as CSV first
            df_csv = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
            if not df_csv.empty and len(df_csv.columns) > 3:
                df = df_csv
                print("File detected as CSV")
            else:
                raise Exception("Not a valid CSV")
        except:
            try:
                # Try with different encoding
                df_csv = pd.read_csv(BytesIO(file_bytes), encoding='latin-1')
                if not df_csv.empty and len(df_csv.columns) > 3:
                    df = df_csv
                    print("File detected as CSV (latin-1 encoding)")
                else:
                    raise Exception("Not a valid CSV")
            except:
                # If CSV fails, try Excel
                if password:
                    # For password-protected Excel files, we need to use openpyxl engine
                    try:
                        import openpyxl
                        # Load workbook with password
                        wb = openpyxl.load_workbook(BytesIO(file_bytes), password=password)
                        # Convert first sheet to DataFrame
                        ws = wb.active
                        data = []
                        for row in ws.iter_rows(values_only=True):
                            data.append(row)
                        df = pd.DataFrame(data)
                    except Exception as e:
                        raise Exception(f"Failed to open password-protected Excel file: {str(e)}")
                else:
                    df = pd.read_excel(BytesIO(file_bytes), sheet_name=0, header=None)
                print("File detected as Excel")
        
        print(f"File loaded. Shape: {df.shape}")
        
        # For Excel files, find the header row
        if 'Excel' in str(type(df)) or df.columns[0] == 0:  # Excel file or headerless
            header_row_index = None
            for i in range(min(30, len(df))):
                row_values = [str(cell).lower().strip() for cell in df.iloc[i] if pd.notna(cell)]
                row_text = ' '.join(row_values)
                
                # Look for different header patterns
                # Original format: Transaction Date, Narration, Debit, Credit
                if ('transaction date' in row_text and 'narration' in row_text and 
                    'debit' in row_text and 'credit' in row_text):
                    header_row_index = i
                    print(f"Found Excel headers (original format) at row {i}")
                    break
                # New format: Date, Description, Withdrawal, Deposit
                elif ('date' in row_text and 'description' in row_text and 
                      'withdrawal' in row_text and 'deposit' in row_text):
                    header_row_index = i
                    print(f"Found Excel headers (new format) at row {i}")
                    break
                # Alternative format: Date, Description, Transaction ID
                elif ('date' in row_text and 'description' in row_text and 
                      ('transaction id' in row_text or 'transaction' in row_text)):
                    header_row_index = i
                    print(f"Found Excel headers (transaction ID format) at row {i}")
                    break
                # Fallback: Just Date and Description
                elif 'date' in row_text and 'description' in row_text:
                    header_row_index = i
                    print(f"Found Excel headers (basic format) at row {i}")
                    break
            
            if header_row_index is None:
                print("Could not find header row with required columns in Excel file")
                return pd.DataFrame(columns=["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"])
            
            # Get the header row to identify column positions
            headers = df.iloc[header_row_index].tolist()
            data_start_row = header_row_index + 1
        else:
            # CSV file - headers are already detected
            headers = df.columns.tolist()
            data_start_row = 0
            print("CSV headers detected automatically")
        
        print(f"Headers found: {headers}")
        
        # Find column indices for all supported formats
        date_col = None
        narration_col = None
        description_col = None
        reference_col = None
        ref_number_col = None
        transaction_id_col = None
        debit_col = None
        credit_col = None
        withdrawal_col = None
        deposit_col = None
        amount_col = None
        
        for i, header in enumerate(headers):
            if pd.isna(header):
                continue
            header_str = str(header).lower().strip()
            print(f"Processing header {i}: '{header}' -> '{header_str}'")
            
            # Date columns
            if 'transaction date' in header_str or header_str == 'date':
                date_col = i
                print(f"  -> Mapped as DATE column")
            
            # Description columns
            elif 'narration' in header_str:
                narration_col = i
                print(f"  -> Mapped as NARRATION column")
            elif 'description' in header_str:
                description_col = i
                print(f"  -> Mapped as DESCRIPTION column")
            
            # Reference columns
            elif 'transaction reference' in header_str:
                reference_col = i
                print(f"  -> Mapped as TRANSACTION REFERENCE column")
            elif header_str in ['ref. number', 'ref.number', 'ref number']:
                ref_number_col = i
                print(f"  -> Mapped as REF. NUMBER column")
            elif 'transaction id' in header_str or header_str in ['transaction id', 'transactionid']:
                transaction_id_col = i
                print(f"  -> Mapped as TRANSACTION ID column")
            elif header_str == 'reference':
                if reference_col is None:  # Prefer "transaction reference" over "reference"
                    reference_col = i
                    print(f"  -> Mapped as REFERENCE column")
            
            # Amount columns
            elif header_str == 'debit':
                debit_col = i
                print(f"  -> Mapped as DEBIT column")
            elif header_str == 'credit':
                credit_col = i
                print(f"  -> Mapped as CREDIT column")
            elif header_str == 'withdrawal' or header_str == 'withdrawals':
                withdrawal_col = i
                print(f"  -> Mapped as WITHDRAWAL column")
            elif header_str == 'deposit' or header_str == 'deposits':
                deposit_col = i
                print(f"  -> Mapped as DEPOSIT column")
            elif header_str == 'amount':
                amount_col = i
                print(f"  -> Mapped as AMOUNT column")
        
        # Determine the best columns to use
        final_date_col = date_col
        final_description_col = narration_col if narration_col is not None else description_col
        final_reference_col = (reference_col if reference_col is not None else 
                              ref_number_col if ref_number_col is not None else 
                              transaction_id_col)
        
        # Determine format type
        has_separate_debit_credit = debit_col is not None and credit_col is not None
        has_withdrawal_deposit = withdrawal_col is not None and deposit_col is not None
        has_single_amount = amount_col is not None
        
        print(f"Column mapping: Date={final_date_col}, Description={final_description_col}, Reference={final_reference_col}")
        if has_separate_debit_credit:
            print(f"Format: Separate Debit/Credit columns - Debit={debit_col}, Credit={credit_col}")
        elif has_withdrawal_deposit:
            print(f"Format: Separate Withdrawal/Deposit columns - Withdrawal={withdrawal_col}, Deposit={deposit_col}")
        elif has_single_amount:
            print(f"Format: Single Amount column - Amount={amount_col}")
        else:
            print("Warning: No amount columns detected")
        
        # Process data rows
        processed_count = 0
        
        for i in range(data_start_row, len(df)):
            try:
                row = df.iloc[i]
                
                # Skip empty rows
                if row.isna().all():
                    continue
                
                # Get date
                date_val = ""
                if final_date_col is not None and not pd.isna(row.iloc[final_date_col]):
                    raw_date = row.iloc[final_date_col]
                    date_val = clean_date(raw_date)
                
                # Skip if no valid date
                if not date_val:
                    continue
                
                # Get description
                description = ""
                if final_description_col is not None and not pd.isna(row.iloc[final_description_col]):
                    description = str(row.iloc[final_description_col]).strip()
                
                # Get reference
                reference = ""
                if final_reference_col is not None and not pd.isna(row.iloc[final_reference_col]):
                    reference = str(row.iloc[final_reference_col]).strip()
                
                # Get amounts - handle all formats
                withdrawals = 0.0
                deposits = 0.0
                
                if has_separate_debit_credit:
                    # Format 1: Separate Debit and Credit columns
                    if debit_col is not None and not pd.isna(row.iloc[debit_col]):
                        withdrawals = to_number(row.iloc[debit_col])
                    
                    if credit_col is not None and not pd.isna(row.iloc[credit_col]):
                        deposits = to_number(row.iloc[credit_col])
                        
                elif has_withdrawal_deposit:
                    # Format 2: Separate Withdrawal and Deposit columns (NEW FORMAT)
                    if withdrawal_col is not None and not pd.isna(row.iloc[withdrawal_col]):
                        withdrawals = to_number(row.iloc[withdrawal_col])
                    
                    if deposit_col is not None and not pd.isna(row.iloc[deposit_col]):
                        deposits = to_number(row.iloc[deposit_col])
                        
                elif has_single_amount:
                    # Format 3: Single Amount column (positive = deposits, negative = withdrawals)
                    if amount_col is not None and not pd.isna(row.iloc[amount_col]):
                        amount_value = to_number(row.iloc[amount_col])
                        if amount_value > 0:
                            deposits = amount_value
                        elif amount_value < 0:
                            withdrawals = abs(amount_value)  # Convert negative to positive
                
                # Add transaction
                transaction = {
                    "Date": date_val,
                    "Withdrawals": withdrawals,
                    "Deposits": deposits,
                    "Payee": "",
                    "Description": description,
                    "Reference Number": reference
                }
                
                rows.append(transaction)
                processed_count += 1
                
                # Debug first few transactions
                if processed_count <= 3:
                    print(f"Transaction {processed_count}: {transaction}")
                
            except Exception as e:
                print(f"Error processing row {i}: {e}")
                continue
        
        print(f"Total transactions processed: {processed_count}")
        
    except Exception as e:
        print(f"Error reading file: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame(columns=["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"])
    
    # Create DataFrame
    result_df = pd.DataFrame(rows)
    
    # Ensure all columns exist
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in result_df.columns:
            if col in ["Withdrawals", "Deposits"]:
                result_df[col] = 0.0
            else:
                result_df[col] = ""
    
    return result_df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]