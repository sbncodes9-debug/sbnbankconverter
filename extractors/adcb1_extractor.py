# extractors/adcb1_extractor.py
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from datetime import datetime


def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except:
        return ""


def to_number(text):
    try:
        return float(text.replace(",", "").strip())
    except:
        return None


def extract_adcb1_data(file_bytes):
    rows = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:

        for page in pdf.pages:
            lines = page.extract_text().split("\n")

            current = None
            desc_buffer = []
            last_balance = None

            for line in lines:
                line = line.strip()

                # Skip headers
                if not line or "Date" in line or "Balance" in line or "الرصيد" in line:
                    continue

                # Start of new transaction (Date at column start)
                if re.match(r"^\d{2}/\d{2}/\d{4}", line):

                    # Save old transaction
                    if current:
                        current["Description"] = " ".join(desc_buffer).strip()
                        rows.append(current)

                    desc_buffer = []

                    date = parse_date(line[:10])

                    # ----- Column-based amount extraction (ADCB layout fix) -----
                    # ----- Column-based amount extraction (ADCB layout fix) -----
                    parts = re.split(r"\s{2,}", line)

                    debit = 0.0
                    credit = 0.0
                    balance = None

                    # First try numeric extraction: if the line contains three or more
                    # monetary values, assume they are Debit, Credit, Balance (last three)
                    # and map them directly. This handles cases where spacing doesn't
                    # split columns reliably.
                    nums = re.findall(r"[\d,]+\.\d{2}", line)
                    if len(nums) >= 3:
                        debit = to_number(nums[-3]) or 0.0
                        credit = to_number(nums[-2]) or 0.0
                        balance = to_number(nums[-1])
                    else:
                        # Fallback: if splitting by multiple spaces produced columns,
                        # use the last three parts as Debit/Credit/Balance when present.
                        if len(parts) >= 6:
                            raw_debit = parts[-3].strip() if parts[-3] is not None else ""
                            raw_credit = parts[-2].strip() if parts[-2] is not None else ""
                            raw_balance = parts[-1].strip() if parts[-1] is not None else ""

                            debit = to_number(raw_debit) if raw_debit else 0.0
                            credit = to_number(raw_credit) if raw_credit else 0.0
                            balance = to_number(raw_balance) if raw_balance else None

                        # If only two numeric values are present, treat as Amount + Balance
                        # and decide debit/credit by comparing balance to last_balance.
                        if len(nums) == 2:
                            amount = to_number(nums[-2])
                            balance = to_number(nums[-1])
                            if amount is not None and last_balance is not None and balance is not None:
                                if balance < last_balance:
                                    debit = amount
                                else:
                                    credit = amount

                    # If both Debit and Credit were detected and are (nearly) identical
                    # it's likely an OCR/spacing duplication — resolve by using the
                    # balance trend (if available). Do NOT change description.
                    if debit and credit and abs(debit - credit) < 0.005:
                        if last_balance is not None and balance is not None:
                            # If balance decreased, it's a withdrawal; keep debit.
                            if balance < last_balance:
                                credit = 0.0
                            else:
                                debit = 0.0
                        else:
                            # No balance history — default to treating as a deposit
                            # (keep credit) and clear debit to avoid duplicates.
                            debit = 0.0

                    # update last_balance for next heuristics
                    last_balance = balance




                    current = {
                        "Date": date,
                        "Withdrawals": debit,
                        "Deposits": credit,
                        "Payee": "",
                        "Description": "",
                        "Reference Number": ""
                    }

                    # Extract reference if exists
                    ref = re.search(r"\b\d{6,}\b", line)
                    if ref:
                        current["Reference Number"] = ref.group(0)

                    # Anything between date and value date is description
                    middle = re.sub(r"^\d{2}/\d{2}/\d{4}", "", line)
                    middle = re.sub(r"\d{2}/\d{2}/\d{4}.*", "", middle).strip()

                    if middle:
                        desc_buffer.append(middle)

                else:
                    # Continue collecting description lines
                    if current:
                        # Stop if value date appears (end of description)
                        if re.search(r"\d{2}/\d{2}/\d{4}", line):
                            continue

                        # Skip garbage
                        if re.search(r"balance|page|الرصيد", line, re.I):
                            continue

                        desc_buffer.append(line)


            # Save last transaction
            if current:
                current["Description"] = " ".join(desc_buffer).strip()
                rows.append(current)

    return pd.DataFrame(rows)
