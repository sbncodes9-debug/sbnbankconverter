# UAE Bank Statement Converter

A Flask web application that converts bank statements from various UAE banks into standardized Excel format.

## 🏦 Supported Banks

- **Emirates NBD** (2 formats)
- **Wio Bank**
- **RAK Bank** (Statement + Credit Card)
- **Pluto Bank**
- **DIB Bank**
- **Bank Misr**
- **ADCB** (Statement + Credit Card, 2 formats)
- **Mashreq Bank** (2 formats)
- **United Arab Bank (UAB)**
- **Emirates Islamic Bank**
- **Bank of Baroda**
- **Other Banks** (Universal extractor)

## ✨ Features

- PDF to Excel conversion
- Password-protected PDF support
- Excel file conversion
- Multiple bank format support
- Clean, standardized output format
- User-friendly web interface

## 📋 Output Format

All statements are converted to a standardized Excel format with columns:
- Date
- Withdrawals
- Deposits
- Payee
- Description
- Reference Number

## 🚀 Deployment

### PythonAnywhere (Recommended)
See `QUICK_START.md` for fast deployment or `PYTHONANYWHERE_DEPLOYMENT.md` for detailed guide.

### Local Development
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run application
python app.py

# Visit http://localhost:5000
```

## 📦 Requirements

- Python 3.10+
- Flask
- pdfplumber
- pandas
- openpyxl
- pytesseract (for OCR features)
- See `requirements.txt` for full list

## 🔒 Security Features

- Password-protected PDF handling
- Encrypted Excel file support
- Error handling for invalid files
- Secure file processing

## 📁 Project Structure

```
bank-statement-converter/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── wsgi.py                # WSGI configuration for deployment
├── extractors/            # Bank-specific extractors
│   ├── emirates_extractor.py
│   ├── wio_extractor.py
│   ├── rakbank_extractor.py
│   ├── baroda_extractor.py
│   └── ... (other extractors)
├── templates/             # HTML templates
│   ├── home.html
│   ├── bank.html
│   ├── excel.html
│   └── error.html
└── static/               # CSS and static files
    └── style.css
```

## 🛠️ Usage

1. Visit the application URL
2. Select your bank from the home page
3. Upload your PDF statement
4. Enter password if the PDF is protected
5. Click "Convert to Excel"
6. Download the converted Excel file

## 🐛 Troubleshooting

### PDF Not Converting
- Ensure PDF is not corrupted
- Check if password is correct
- Verify bank format is supported

### Missing Data
- Some PDFs may have non-standard formats
- Try the "Other Banks" option for universal extraction

### Deployment Issues
- Check error logs in PythonAnywhere
- Verify all dependencies installed
- Ensure virtual environment is activated

## 📝 License

This project is for internal use. All rights reserved.

## 🤝 Support

For issues or questions, please contact the development team.

## 🔄 Updates

To update the application:
1. Pull latest changes (if using Git)
2. Install any new dependencies
3. Reload the web app in PythonAnywhere

## 📊 Version History

- **v1.0** - Initial release with multiple bank support
- **v1.1** - Added password protection support
- **v1.2** - Added Bank of Baroda support
- **v1.3** - Enhanced column detection and amount extraction
