from flask import Flask, request, send_file, render_template
from io import BytesIO
import pandas as pd

from extractors.emirates_extractor import extract_emirates_data
from extractors.wio_extractor import extract_wio_data
from extractors.rakbank_extractor import extract_rakbank_data
from extractors.dib_extractor import extract_dib_data
from extractors.misr_extractor import extract_misr_data
from extractors.adcb1_extractor import extract_adcb1_data
from extractors.adcb2_extractor import extract_adcb2_data
from extractors.adcb_cc_extractor import extract_adcb_cc_data
from extractors.mashreq_extractor import extract_mashreq_data
from extractors.emirates2_extractor import extract_emirates2_data
from extractors.universal_extractor import extract_universal_data
from extractors.mashreq_format2_extractor import extract_mashreq_format2_data
from extractors.uab_extractor import extract_uab_data
from extractors.excel_extractor import extract_excel_data



app = Flask(__name__)


# -------------------------------------------------------------------
# HOME PAGE
# -------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


# -------------------------------------------------------------------
# GENERIC BANK HANDLER
# -------------------------------------------------------------------
def process_bank(request, extractor_func, download_filename):
    file = request.files["pdf"]
    df = extractor_func(file.read())

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name=download_filename, as_attachment=True)


# -------------------------------------------------------------------
# BANK ROUTES
# -------------------------------------------------------------------
@app.route("/emirates", methods=["GET", "POST"])
def emirates():
    if request.method == "POST":
        return process_bank(request, extract_emirates_data, "emirates_statement.xlsx")
    return render_template("bank.html", bank_name="Emirates NBD")


@app.route("/wio", methods=["GET", "POST"])
def wio():
    if request.method == "POST":
        return process_bank(request, extract_wio_data, "wio_statement.xlsx")
    return render_template("bank.html", bank_name="Wio Bank")


@app.route("/rakbank", methods=["GET", "POST"])
def rakbank():
    if request.method == "POST":
        return process_bank(request, extract_rakbank_data, "rakbank_statement.xlsx")
    return render_template("bank.html", bank_name="RAK Bank")


@app.route("/dib", methods=["GET", "POST"])
def dib():
    if request.method == "POST":
        return process_bank(request, extract_dib_data, "dib_statement.xlsx")
    return render_template("bank.html", bank_name="DIB Bank")



@app.route("/misr", methods=["GET", "POST"])
def misr():
    if request.method == "POST":
        return process_bank(request, extract_misr_data, "misr_statement.xlsx")
    return render_template("bank.html", bank_name="Bank Misr")


@app.route("/adcb1", methods=["GET", "POST"])
def adcb1():
    if request.method == "POST":
        return process_bank(request, extract_adcb1_data, "adcb_format1.xlsx")
    return render_template("bank.html", bank_name="ADCB Format 1")


@app.route("/adcb2", methods=["GET", "POST"])
def adcb2():
    if request.method == "POST":
        return process_bank(request, extract_adcb2_data, "adcb_format2.xlsx")
    return render_template("bank.html", bank_name="ADCB Format 2")


@app.route("/adcb_cc", methods=["GET", "POST"])
def adcb_cc():
    if request.method == "POST":
        return process_bank(request, extract_adcb_cc_data, "adcb_credit_card.xlsx")
    return render_template("bank.html", bank_name="ADCB Credit Card")


@app.route("/mashreq", methods=["GET", "POST"])
def mashreq():
    if request.method == "POST":
        return process_bank(request, extract_mashreq_data, "mashreq_statement.xlsx")
    return render_template("bank.html", bank_name="Mashreq Bank")

@app.route("/emirates2", methods=["GET", "POST"])
def emirates2():
    if request.method == "POST":
        return process_bank(request, extract_emirates2_data, "emirates2_statement.xlsx")
    return render_template("bank.html", bank_name="Emirates NBD Format 2")

@app.route("/otherbanks", methods=["GET", "POST"])
def otherbanks():
    if request.method == "POST":
        return process_bank(
            request,
            extract_universal_data,
            "other_banks_statement.xlsx"
        )
    return render_template("bank.html", bank_name="Other Banks")

@app.route("/mashreq2", methods=["GET", "POST"])
def mashreq2():
    if request.method == "POST":
        return process_bank(
            request,
            extract_mashreq_format2_data,
            "mashreq_format2_statement.xlsx"
        )
    return render_template("bank.html", bank_name="Mashreq Bank (Format 2)")


@app.route("/uab", methods=["GET", "POST"])
def uab():
    if request.method == "POST":
        return process_bank(
            request,
            extract_uab_data,
            "uab_statement.xlsx"
        )
    return render_template("bank.html", bank_name="United Arab Bank (UAB)")


@app.route("/excel", methods=["GET", "POST"])
def excel():
    if request.method == "POST":
        return process_excel(request)
    return render_template("excel.html")


# -------------------------------------------------------------------
# EXCEL PROCESSOR
# -------------------------------------------------------------------
def process_excel(request):
    file = request.files["excel"]
    df = extract_excel_data(file.read())

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name="converted_excel_statement.xlsx", as_attachment=True)


# -------------------------------------------------------------------
# RUN APP (Render compatible)
# -------------------------------------------------------------------
if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000)
