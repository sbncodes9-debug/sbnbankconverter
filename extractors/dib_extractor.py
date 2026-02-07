# extractors/dib_extractor.py
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


IGNORE_KEYWORDS = [
    "available balance",
    "statement date",
    "if your card",
    "phone banking",
    "online banking",
    "mobile banking"
]


def clean_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        text = re.sub(r"[^\d.,]", "", text)
        text = text.replace(",", "")
        return float(text)
    except:
        return 0.0


def extract_dib_data(file_bytes, password=None):
    rows = []

    with pdfplumber.open(BytesIO(file_bytes), password=password) as pdf:
        for page in pdf.pages:

            words = page.extract_words(use_text_flow=True, keep_blank_chars=True)

            if not words:
                continue

            # ----- Detect column X positions -----
            # ----- Detect column X positions (DIB stable scan) -----
            debit_x = None
            credit_x = None
            ref_x_range = None

            for w in words:
                txt = w["text"].strip().lower()
                x0 = float(w["x0"])
                x1 = float(w["x1"])

                if "debit" in txt and debit_x is None:
                    debit_x = x0

                elif "credit" in txt and credit_x is None:
                    credit_x = x0

                # DIB reference column usually before description
                elif "chq" in txt or "ref" in txt:
                    if ref_x_range is None:
                        ref_x_range = (x0 - 10, x1 + 10)


            # Group words by line
            lines = {}
            for w in words:
                top = round(float(w["top"]), 1)
                lines.setdefault(top, []).append(w)

            sorted_lines = sorted(lines.items(), key=lambda x: x[0])

            current = None

            for _, word_list in sorted_lines:
                word_list.sort(key=lambda w: float(w["x0"]))
                line_text = clean_text(" ".join(w["text"] for w in word_list))

                if not line_text:
                    continue

                # Skip footer lines
                if any(k.lower() in line_text.lower() for k in IGNORE_KEYWORDS):
                    continue

                # Start of a new transaction
                if re.match(r"^\d{2} [A-Za-z]{3} \d{4}", line_text):

                    # Save previous row
                    if current:
                        rows.append(current)

                    # --- Date ---
                    tran_date = parse_date(line_text[:11])

                    # --- Reference Number by column position ---
                    ref_no = ""
                    description_parts = []
                    debit = 0.0
                    credit = 0.0

                    for w in word_list:
                        x0 = float(w["x0"])
                        txt = w["text"]

                        # Reference column by X range
                        if ref_x_range and ref_x_range[0] <= x0 <= ref_x_range[1]:
                            if re.search(r"\w{5,}", txt):
                                ref_no += txt

                        # Debit column
                        if debit_x and abs(x0 - debit_x) < 25 and re.search(r"[\d,]+\.\d{2}", txt):
                            debit = to_number(txt)

                        # Credit column
                        if credit_x and abs(x0 - credit_x) < 25 and re.search(r"[\d,]+\.\d{2}", txt):
                            credit = to_number(txt)

                        # Description column
                        if x0 > (ref_x_range[1] if ref_x_range else 0) and \
                           (debit_x is None or x0 < debit_x):
                            description_parts.append(txt)

                    # --- Clean description ---
                    desc = clean_text(" ".join(description_parts))
                    desc = re.sub(r"\d{2}\s[A-Za-z]{3}\s\d{4}", "", desc)
                    desc = re.sub(r"[\d,]+\.\d{2}", "", desc)

                    current = {
                        "Date": tran_date,
                        "Withdrawals": debit,
                        "Deposits": credit,
                        "Payee": "",
                        "Description": desc,
                        "Reference Number": ref_no.strip()
                    }

                else:
                    # Continuation lines — add only real description
                    if current:
                        if any(x in line_text.lower() for x in [
                            "statement of account",
                            "available balance",
                            "central bank",
                            "islamic bank"
                        ]):
                            continue

                        if re.match(r"\d{2} [A-Za-z]{3} \d{4}", line_text):
                            continue

                        # Clean continuation line
                        extra = re.sub(r"\d{2}\s[A-Za-z]{3}\s\d{4}", "", line_text)
                        extra = re.sub(r"[\d,]+\.\d{2}", "", extra)

                        current["Description"] += " " + extra

            # Save last row
            if current:
                rows.append(current)

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"
        ])

    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
