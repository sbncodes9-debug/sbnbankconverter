# extractors/rakbank_extractor.py
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


IGNORE_KEYWORDS = [
    "Your Bank Statement", "Statement Period", "Account Number",
    "The National Bank of Ras Al Khaimah", "Islamic Banking",
    "Division", "Central Bank", "Currency", "Branch",
    "Your Current Account Transactions", "Balance", "Page", "Date Issued"
]


def is_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def clean_text(s: str) -> str:
    if not s:
        return ""
    # remove weird multi-space and non-ascii (keeps punctuation)
    s = re.sub(r"\s+", " ", s).strip()
    # keep ascii and common punctuation; remove isolated control chars
    return s


def parse_date(text: str) -> str:
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text: str) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except:
        return 0.0


def extract_rakbank_data(file_bytes):
    """
    Column-position extractor:
    - Finds header positions for Date / Description / Withdrawal / Deposit
    - Uses those x positions to slice every visual row into columns
    - Multi-line descriptions (lines above a date) are concatenated into next transaction
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

            # find header line: look for a line that contains Date & Withdrawal & Deposit (case-insensitive)
            header_line_top = None
            header_positions = {}
            for top, word_list in sorted_lines[:40]:  # only scan top portion of page
                texts = [w["text"].lower() for w in word_list]
                if any("date" == t or "التاريخ" in t for t in texts) and \
                   any("withdrawal" in t or "السحب" in t for t in texts) and \
                   any("deposit" in t or "الوديعة" in t for t in texts):
                    header_line_top = top
                    for w in word_list:
                        t = w["text"].lower()
                        if "date" == t or "التاريخ" in t:
                            header_positions["date"] = float(w["x0"])
                        if "description" in t or "الوصف" in t:
                            header_positions["description"] = float(w["x0"])
                        if "withdrawal" in t or "السحب" in t:
                            header_positions["withdrawal"] = float(w["x0"])
                        if "deposit" in t or "الوديعة" in t:
                            header_positions["deposit"] = float(w["x0"])
                    break

            # if header not found, fallback: try to infer by approximate x positions using the first line
            if not header_positions:
                # take the first real text line (skip visible metadata)
                header_candidates = None
                for top, word_list in sorted_lines[:60]:
                    texts = " ".join(w["text"] for w in word_list)
                    if len(texts) > 20 and not any(k.lower() in texts.lower() for k in IGNORE_KEYWORDS):
                        header_candidates = word_list
                        break
                if header_candidates:
                    # take first few x0 positions: assume columns at increasing x0
                    xs = sorted(set(round(w["x0"], 1) for w in header_candidates))
                    # heuristics if we have >=4 columns
                    if len(xs) >= 4:
                        header_positions["date"] = xs[0]
                        header_positions["description"] = xs[1]
                        header_positions["withdrawal"] = xs[-2]
                        header_positions["deposit"] = xs[-1]  # may be last numeric column
                    else:
                        # fallback fixed positions (works for typical RAK PDF widths)
                        header_positions = {
                            "date": 40.0,
                            "description": 150.0,
                            "withdrawal": 420.0,
                            "deposit": 520.0
                        }

            # build column boundaries (midpoints between header x's)
            # ensure keys exist
            for k in ["date", "description", "withdrawal", "deposit"]:
                if k not in header_positions:
                    # set sensible defaults
                    if k == "date":
                        header_positions[k] = 40.0
                    elif k == "description":
                        header_positions[k] = 150.0
                    elif k == "withdrawal":
                        header_positions[k] = 420.0
                    else:
                        header_positions[k] = 520.0

            # create ranges: left/right boundaries for each column
            # sort keys by x
            items = sorted(header_positions.items(), key=lambda x: x[1])
            xs = [p for _, p in items]
            mids = []
            for i in range(len(xs) - 1):
                mids.append((xs[i] + xs[i + 1]) / 2.0)
            # set boundaries:
            # date: (-inf, mids[0]); description: (mids[0], mids[1]); withdrawal: (mids[1], mids[2]); deposit: (mids[2], +inf)
            # if less mids, fill with defaults
            while len(mids) < 3:
                mids.append(mids[-1] + 120 if mids else 300.0)

            date_r = (-9999, mids[0])
            desc_r = (mids[0], mids[1])
            wd_r = (mids[1], mids[2])
            dep_r = (mids[2], 99999)

            # helper to map a word x to column
            def which_col(x):
                if x < date_r[1]:
                    return "date"
                if date_r[1] <= x < desc_r[1]:
                    return "description"
                if desc_r[1] <= x < wd_r[1]:
                    return "withdrawal"
                return "deposit"

            # now iterate visual rows and build transactions
            desc_lines = []   # accumulate description lines for current transaction
            current = None

            # skip header rows until header_line_top if header_line_top found
            started = False if header_line_top else True

            for top, word_list in sorted_lines:
                # skip header region
                if header_line_top and top <= header_line_top:
                    continue

                # build a map of column -> joined text for this visual row
                row_cols = {"date": "", "description": "", "withdrawal": "", "deposit": ""}
                for w in sorted(word_list, key=lambda w: w["x0"]):
                    text = w["text"].strip()
                    if not text:
                        continue
                    if is_arabic(text) and len(text) < 4:
                        # ignore tiny Arabic fragments
                        continue
                    col = which_col(float(w["x0"]))
                    if row_cols[col]:
                        row_cols[col] += " " + text
                    else:
                        row_cols[col] = text

                # skip rows that are clearly header/footer or junk
                joined = " ".join(row_cols.values())
                if not joined or any(k.lower() in joined.lower() for k in IGNORE_KEYWORDS):
                    continue

                # if this row has a date field, it's a new transaction row
                date_text = row_cols["date"].strip()
                if re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}", date_text):
                    # flush previous transaction with accumulated descriptions
                    if current:
                        # join all accumulated description lines
                        current["Description"] = clean_text(" ".join(desc_lines)) if desc_lines else current["Description"]
                        rows.append(current)
                    
                    # reset description buffer for new transaction
                    desc_lines = []

                    # start new transaction
                    current = {
                        "Date": parse_date(date_text),
                        "Withdrawals": 0.0,
                        "Deposits": 0.0,
                        "Payee": "",
                        "Description": clean_text(row_cols["description"]),
                        "Reference Number": ""
                    }
                    
                    # add inline description to accumulator
                    if row_cols["description"].strip():
                        desc_lines.append(clean_text(row_cols["description"]))

                    # parse numeric strings in withdrawal / deposit column exactly as they appear
                    wd_txt = row_cols["withdrawal"].replace("Cr.", "").replace("Dr.", "").strip()
                    dp_txt = row_cols["deposit"].replace("Cr.", "").replace("Dr.", "").strip()

                    # convert only if field non-empty and looks like number
                    if re.search(r"\d", wd_txt):
                        # keep digits and punctuation
                        num_match = re.search(r"-?[\d,]+\.\d{2}", wd_txt)
                        if num_match:
                            current["Withdrawals"] = to_number(num_match.group(0))

                    # DEPOSIT – only accept if this is NOT a running balance
                    if re.search(r"\d", dp_txt):
                        # Reject if this looks like a running balance (very large number)
                        test_num = re.search(r"-?[\d,]+\.\d{2}", dp_txt)
                        if test_num:
                            val = to_number(test_num.group(0))
                            # Ignore unrealistic large numbers (running balance)
                            if val <= 200000:  
                                current["Deposits"] = val

                else:
                    # no date in this visual row → likely description continuation
                    desc_text = row_cols["description"].strip()
                    # ignore rows that look like page footer etc.
                    if desc_text and not is_arabic(desc_text) and not any(k.lower() in desc_text.lower() for k in IGNORE_KEYWORDS):
                        # accumulate description line for current transaction
                        if current:
                            desc_lines.append(clean_text(desc_text))
                    
                    # Also some pdfs put amount on separate line below description — handle that:
                    # if withdrawal/deposit present on a non-date line, and there is a current transaction, assign amount (rare)
                    if current:
                        wd_txt = row_cols["withdrawal"]
                        dp_txt = row_cols["deposit"]
                        if wd_txt and re.search(r"-?[\d,]+\.\d{2}", wd_txt):
                            m = re.search(r"-?[\d,]+\.\d{2}", wd_txt)
                            current["Withdrawals"] = to_number(m.group(0))
                        if dp_txt and re.search(r"-?[\d,]+\.\d{2}", dp_txt):
                            m = re.search(r"-?[\d,]+\.\d{2}", dp_txt)
                            current["Deposits"] = to_number(m.group(0))
                    # Also some pdfs put amount on separate line below description — handle that:
                    # if withdrawal/deposit present on a non-date line, and there is a current transaction, assign amount (rare)
                    if current:
                        wd_txt = row_cols["withdrawal"]
                        dp_txt = row_cols["deposit"]
                        if wd_txt and re.search(r"-?[\d,]+\.\d{2}", wd_txt):
                            m = re.search(r"-?[\d,]+\.\d{2}", wd_txt)
                            current["Withdrawals"] = to_number(m.group(0))
                        if dp_txt and re.search(r"-?[\d,]+\.\d{2}", dp_txt):
                            m = re.search(r"-?[\d,]+\.\d{2}", dp_txt)
                            current["Deposits"] = to_number(m.group(0))

            # after page loop, flush last current
            if current:
                # join all accumulated description lines
                current["Description"] = clean_text(" ".join(desc_lines)) if desc_lines else current["Description"]
                rows.append(current)

    # final dataframe and column order
    df = pd.DataFrame(rows)
    # ensure columns exist even if empty
    for col in ["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]:
        if col not in df.columns:
            df[col] = "" if col in ["Payee", "Description", "Reference Number"] else 0.0

    df = df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
    return df
