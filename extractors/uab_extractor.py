import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


IGNORE_KEYWORDS = [
    "Account Statement", "Statement of Account", "Account Number", "STATEMENT OF ACCOUNT",
    "UAB", "United Arab Bank", "Branch", "Currency", "IBAN", "Customer Number",
    "Account Type", "Dear Customer", "Page", "Balance", "Opening balance", "Closing balance",
    "Balance Carried forward", "Period", "UAE Dirham", "Current Account"
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
    """Convert dd.mm.yyyy to dd-mm-yyyy"""
    try:
        if re.match(r'^\d{2}\.\d{2}\.\d{4}', text):
            day, month, year = text.split('.')
            return f"{day}-{month}-{year}"
        return text
    except:
        return ""


def to_number(text: str) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except:
        return 0.0


def extract_uab_data(file_bytes):
    """
    Column-position extractor for UAB Bank statements
    Format: Date | Description | Debit | Credit | Balance
    """
    rows = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # extract words with coordinates
            words = page.extract_words(use_text_flow=True)

            if not words:
                continue

            # group words by rounded top (visual rows)
            lines = {}
            for w in words:
                top = round(float(w["top"]), 1)
                lines.setdefault(top, []).append(w)

            # sort lines top → bottom
            sorted_lines = sorted(lines.items(), key=lambda x: x[0])

            # find header line: look for both English and Arabic headers
            header_line_top = None
            header_positions = {}
            for top, word_list in sorted_lines[:40]:  # only scan top portion of page
                texts = [w["text"].lower() for w in word_list]
                arabic_texts = [w["text"] for w in word_list]
                
                # Look for Arabic headers which are positioned above the actual amounts
                if any("مدين" in t for t in arabic_texts) and any("دائن" in t for t in arabic_texts):
                    header_line_top = top
                    for w in word_list:
                        t = w["text"]
                        if "date" in w["text"].lower() or "التاريخ" in t:
                            header_positions["date"] = float(w["x0"])
                        if "description" in w["text"].lower() or "التفاصيل" in t:
                            header_positions["description"] = float(w["x0"])
                        if "مدين" in t:  # Arabic for Debit
                            header_positions["debit"] = float(w["x0"])
                        if "دائن" in t:  # Arabic for Credit
                            header_positions["credit"] = float(w["x0"])
                        if "balance" in w["text"].lower() or "الرصيد" in t:
                            header_positions["balance"] = float(w["x0"])
                    break
                # Fallback to English headers if Arabic not found
                elif any("date" == t or "التاريخ" in t for t in texts) and \
                     any("debit" in t or "قيود" in t for t in texts) and \
                     any("credit" in t or "دائنه" in t for t in texts):
                    header_line_top = top
                    for w in word_list:
                        t = w["text"].lower()
                        if "date" == t or "التاريخ" in w["text"]:
                            header_positions["date"] = float(w["x0"])
                        if "description" in t or "التفاصيل" in w["text"]:
                            header_positions["description"] = float(w["x0"])
                        if "debit" in t or "قيود" in w["text"]:
                            header_positions["debit"] = float(w["x0"])
                        if "credit" in t or "دائنه" in w["text"]:
                            header_positions["credit"] = float(w["x0"])
                        if "balance" in t or "الرصيد" in w["text"]:
                            header_positions["balance"] = float(w["x0"])
                    break

            # if header not found, use fallback positions based on UAB format
            if not header_positions:
                header_positions = {
                    "date": 60.0,
                    "description": 150.0,
                    "debit": 420.0,
                    "credit": 480.0,
                    "balance": 580.0
                }

            # build column boundaries (midpoints between header x's)
            # ensure keys exist
            for k in ["date", "description", "debit", "credit", "balance"]:
                if k not in header_positions:
                    # set sensible defaults for UAB format
                    if k == "date":
                        header_positions[k] = 60.0
                    elif k == "description":
                        header_positions[k] = 150.0
                    elif k == "debit":
                        header_positions[k] = 420.0
                    elif k == "credit":
                        header_positions[k] = 480.0
                    else:  # balance
                        header_positions[k] = 580.0

            # create ranges: left/right boundaries for each column
            # Based on UAB PDF structure: Date | Description | Debit | Credit | Balance
            items = sorted(header_positions.items(), key=lambda x: x[1])
            xs = [p for _, p in items]
            mids = []
            for i in range(len(xs) - 1):
                mids.append((xs[i] + xs[i + 1]) / 2.0)
            # ensure we have enough boundaries
            while len(mids) < 4:
                mids.append(mids[-1] + 60 if mids else 400.0)

            # Use header detection for column boundaries
            # Based on UAB PDF structure: Date | Description | Debit | Credit | Balance
            items = sorted(header_positions.items(), key=lambda x: x[1])
            xs = [p for _, p in items]
            mids = []
            for i in range(len(xs) - 1):
                mids.append((xs[i] + xs[i + 1]) / 2.0)
            # ensure we have enough boundaries
            while len(mids) < 4:
                mids.append(mids[-1] + 60 if mids else 400.0)

            # Apply column boundaries with gap between description and debit to prevent overlap
            date_r = (-9999, mids[0])
            desc_r = (mids[0], mids[1] - 30)  # Description column ends 30px before debit to prevent overlap
            debit_r = (mids[1] - 10, mids[2] + 20)  # Debit column = Withdrawals - starts slightly earlier, wider
            credit_r = (mids[2], mids[3] + 20)  # Credit column = Deposits - wider to capture amounts
            balance_r = (mids[3] + 20, 99999)  # Balance column (ignore)

            # helper to map a word x to column
            def which_col(x):
                if x < date_r[1]:
                    return "date"
                if date_r[1] <= x < desc_r[1]:
                    return "description"
                if desc_r[1] <= x < debit_r[1]:
                    return "debit"
                if debit_r[1] <= x < credit_r[1]:
                    return "credit"
                return "balance"  # Ignore balance column

            # Helper function to get description between two dates
            def get_description_between_dates(start_y, end_y):
                """Extract description text between two date positions with no overlap"""
                # Start slightly above the date line to capture descriptions that begin above
                actual_start_y = start_y - 15  # Start 15 pixels above the date line
                
                # Get page height to determine footer area
                page_height = page.height if hasattr(page, 'height') else 800
                footer_threshold = page_height - 100  # Bottom 100 pixels are footer
                
                description_parts = []
                for top, word_list in sorted_lines:
                    # Skip footer area completely
                    if top > footer_threshold:
                        continue
                        
                    if actual_start_y < top < end_y:  # Start above date, end before next date
                        for w in sorted(word_list, key=lambda x: x["x0"]):
                            text = w["text"].strip()
                            x_pos = float(w["x0"])
                            
                            # Only collect text from description column
                            if (desc_r[0] <= x_pos < desc_r[1]) and text and not is_arabic(text):
                                # Skip if it's a date format
                                if not re.match(r'^\d{2}\.\d{2}\.\d{4}', text):
                                    # Additional check: skip if text contains any Arabic characters
                                    if not re.search(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text):
                                        description_parts.append(text)
                
                # Join all description parts and clean
                full_text = " ".join(description_parts)
                
                # Remove Arabic text more comprehensively - multiple passes
                # Remove Arabic characters (main Arabic block)
                full_text = re.sub(r'[\u0600-\u06FF]', '', full_text)
                # Remove Arabic Supplement
                full_text = re.sub(r'[\u0750-\u077F]', '', full_text)
                # Remove Arabic Extended-A
                full_text = re.sub(r'[\u08A0-\u08FF]', '', full_text)
                # Remove Arabic Presentation Forms-A
                full_text = re.sub(r'[\uFB50-\uFDFF]', '', full_text)
                # Remove Arabic Presentation Forms-B
                full_text = re.sub(r'[\uFE70-\uFEFF]', '', full_text)
                
                # Additional aggressive Arabic removal - any remaining Arabic-like patterns
                full_text = re.sub(r'[^\x00-\x7F]+', '', full_text)  # Remove all non-ASCII characters
                
                # Remove common non-description words and specific Arabic phrases
                full_text = re.sub(r'\b(?:Balance|الرصيد|Debit|Credit|مدين|دائن)\b', '', full_text)
                # Remove specific Arabic phrase
                full_text = re.sub(r'يزكرملا ةدحتملا ةيبرعلا', '', full_text)
                full_text = re.sub(r'ةيبرعلا ةدحتملا يزكرملا', '', full_text)  # In case word order is different
                
                # Clean up extra spaces and punctuation left by Arabic removal
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                full_text = re.sub(r'[^\w\s\-\.\,\:\;\/\(\)]+', ' ', full_text)  # Keep only alphanumeric, spaces, and common punctuation
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                
                return full_text

            # First pass: collect all date positions
            date_positions = []
            for top, word_list in sorted_lines:
                if header_line_top and top <= header_line_top:
                    continue
                    
                for w in word_list:
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}', w["text"].strip()):
                        date_positions.append(top)
                        break
            
            date_positions.sort()

            # now iterate visual rows and build transactions
            current = None

            for top, word_list in sorted_lines:
                # skip header region
                if header_line_top and top <= header_line_top:
                    continue

                # build a map of column -> joined text for this visual row
                row_cols = {"date": "", "description": "", "debit": "", "credit": "", "balance": ""}
                for w in sorted(word_list, key=lambda w: w["x0"]):
                    text = w["text"].strip()
                    if not text:
                        continue
                    if is_arabic(text) and len(text) < 4:
                        # ignore tiny Arabic fragments
                        continue
                    col = which_col(float(w["x0"]))
                    if col == "balance":  # Skip balance column completely
                        continue
                    if col in row_cols:
                        if row_cols[col]:
                            row_cols[col] += " " + text
                        else:
                            row_cols[col] = text

                # skip rows that are clearly header/footer or junk
                joined = " ".join(row_cols.values())
                if not joined or any(k.lower() in joined.lower() for k in IGNORE_KEYWORDS):
                    continue

                # if this row has a date field (dd.mm.yyyy format), it's a new transaction row
                date_text = row_cols["date"].strip()
                if re.match(r"^\d{2}\.\d{2}\.\d{4}", date_text):
                    # flush previous transaction
                    if current:
                        rows.append(current)
                    
                    # Get description between current date and next date
                    current_y = top
                    next_y = 99999  # Default to end of page
                    
                    # Find next date position
                    for i, date_y in enumerate(date_positions):
                        if date_y == current_y and i + 1 < len(date_positions):
                            next_y = date_positions[i + 1]
                            break
                    
                    # Get description between dates with no overlap
                    complete_description = get_description_between_dates(current_y, next_y)
                    
                    # start new transaction
                    current = {
                        "Date": parse_date(date_text),
                        "Withdrawals": 0.0,
                        "Deposits": 0.0,
                        "Payee": "",
                        "Description": clean_text(complete_description),
                        "Reference Number": ""
                    }

                    # parse numeric strings in debit / credit columns
                    debit_txt = row_cols["debit"].strip()
                    credit_txt = row_cols["credit"].strip()

                    # Debit column -> Withdrawals
                    if re.search(r"\d", debit_txt):
                        # Only capture amounts in format like 2,352.00 or 1,234.56 (with commas and decimals)
                        num_match = re.search(r"\d{1,3}(?:,\d{3})*\.\d{2}", debit_txt)
                        if num_match:
                            current["Withdrawals"] = to_number(num_match.group(0))

                    # Credit column -> Deposits
                    if re.search(r"\d", credit_txt):
                        # Only capture amounts in format like 2,352.00 or 1,234.56 (with commas and decimals)
                        num_match = re.search(r"\d{1,3}(?:,\d{3})*\.\d{2}", credit_txt)
                        if num_match:
                            current["Deposits"] = to_number(num_match.group(0))

                else:
                    # This is a continuation line for description
                    if current and row_cols["description"].strip():
                        # Add to existing description with space
                        if current["Description"]:
                            current["Description"] += " " + clean_text(row_cols["description"])
                        else:
                            current["Description"] = clean_text(row_cols["description"])

            # after page loop, flush last current
            if current:
                rows.append(current)

    # final dataframe and column order
    df = pd.DataFrame(rows)
    
    # Remove balance entries
    if not df.empty:
        df = df[~df['Description'].str.contains('balance|opening|closing|carried forward', case=False, na=False)]
    
    # ensure columns exist even if empty
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            df[col] = "" if col in ["Payee", "Description", "Reference Number"] else 0.0

    df = df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]    
    return df