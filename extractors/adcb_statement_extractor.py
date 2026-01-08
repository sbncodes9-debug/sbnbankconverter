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
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        return float(text.replace(",", "").strip())
    except:
        return 0.0


def extract_adcb_statement_data(file_bytes):
    """
    ADCB Statement of Accounts extractor with OCR support
    """
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
            return pd.DataFrame(columns=[
                "Date", "Withdrawals", "Deposits",
                "Payee", "Description", "Reference Number"
            ])

        # Detect transaction starts
        txn_matches = list(re.finditer(
            r"^\d+\s+\d{2}-[A-Za-z]{3}-\d{4}",
            full_text,
            re.M
        ))

        if not txn_matches:
            return pd.DataFrame(columns=[
                "Date", "Withdrawals", "Deposits",
                "Payee", "Description", "Reference Number"
            ])

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

                date = parse_date(header[1])
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
                # Skip bad transaction blocks safely
                continue

    except Exception:
        # Absolute safety net
        return pd.DataFrame(columns=[
            "Date", "Withdrawals", "Deposits",
            "Payee", "Description", "Reference Number"
        ])

    df = pd.DataFrame(rows)
    return df[["Date", "Withdrawals", "Deposits", "Payee", "Description", "Reference Number"]]
