from flask import Flask, request, send_file, render_template
from io import BytesIO
import pandas as pd

from extractors.emirates_extractor import extract_emirates_data
from extractors.wio_extractor import extract_wio_data
from extractors.rakbank_extractor import extract_rakbank_data
from extractors.rakbank_cc_extractor import extract_rakbank_cc_data
from extractors.pluto_extractor import extract_pluto_data
from extractors.dib_extractor import extract_dib_data
from extractors.misr_extractor import extract_misr_data
from extractors.adcb_cc_extractor import extract_adcb_cc_data
from extractors.mashreq_extractor import extract_mashreq_data
from extractors.emirates2_extractor import extract_emirates2_data
from extractors.universal_extractor import extract_universal_data
from extractors.mashreq_format2_extractor import extract_mashreq_format2_data
from extractors.uab_extractor import extract_uab_data
from extractors.excel_extractor import extract_excel_data
from extractors.adcb_statement_extractor import extract_adcb_statement_data
from extractors.emirates_islamic_extractor import extract_emirates_islamic_data
from extractors.baroda_extractor import extract_baroda_data



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
    password = request.form.get("password", "")  # Get password from form, default to empty string
    
    try:
        # Pass password to extractor function
        df = extractor_func(file.read(), password if password else None)
        
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        
        return send_file(output, download_name=download_filename, as_attachment=True)
    
    except Exception as e:
        # Handle password-related errors
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg or "locked" in error_msg:
            return render_template("error.html", 
                                 error_message="PDF is password-protected. Please provide the correct password.",
                                 back_url=request.url), 400
        else:
            return render_template("error.html", 
                                 error_message=f"Error processing PDF: {str(e)}",
                                 back_url=request.url), 500


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


@app.route("/rakbank_cc", methods=["GET", "POST"])
def rakbank_cc():
    if request.method == "POST":
        return process_bank(request, extract_rakbank_cc_data, "rakbank_credit_card.xlsx")
    return render_template("bank.html", bank_name="RAK Bank Credit Card")


@app.route("/pluto", methods=["GET", "POST"])
def pluto():
    if request.method == "POST":
        return process_bank(request, extract_pluto_data, "pluto_statement.xlsx")
    return render_template("bank.html", bank_name="Pluto Bank")


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
        return process_bank(request, extract_adcb_statement_data, "adcb_format1.xlsx")
    return render_template("bank.html", bank_name="ADCB Format 1")


@app.route("/adcb2", methods=["GET", "POST"])
def adcb2():
    if request.method == "POST":
        return process_bank(request, extract_adcb_statement_data, "adcb_format2.xlsx")
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


@app.route("/adcb_statement", methods=["GET", "POST"])
def adcb_statement():
    if request.method == "POST":
        return process_bank(
            request,
            extract_adcb_statement_data,
            "adcb_statement.xlsx"
        )
    return render_template("bank.html", bank_name="ADCB Bank")


@app.route("/emirates_islamic", methods=["GET", "POST"])
def emirates_islamic():
    if request.method == "POST":
        return process_bank(
            request,
            extract_emirates_islamic_data,
            "emirates_islamic_statement.xlsx"
        )
    return render_template("bank.html", bank_name="Emirates Islamic Bank")


@app.route("/baroda", methods=["GET", "POST"])
def baroda():
    if request.method == "POST":
        return process_bank(
            request,
            extract_baroda_data,
            "baroda_statement.xlsx"
        )
    return render_template("bank.html", bank_name="Bank of Baroda")


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
    password = request.form.get("password", "")  # Get password from form, default to empty string
    
    try:
        # Pass password to extractor function
        df = extract_excel_data(file.read(), password if password else None)
        
        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        
        return send_file(output, download_name="converted_excel_statement.xlsx", as_attachment=True)
    
    except Exception as e:
        # Handle password-related errors
        error_msg = str(e).lower()
        if "password" in error_msg or "encrypted" in error_msg or "locked" in error_msg:
            return render_template("error.html", 
                                 error_message="Excel file is password-protected. Please provide the correct password.",
                                 back_url="/excel"), 400
        else:
            return render_template("error.html", 
                                 error_message=f"Error processing Excel file: {str(e)}",
                                 back_url="/excel"), 500


# -------------------------------------------------------------------
# RUN APP (Render compatible)
# -------------------------------------------------------------------
if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000)
