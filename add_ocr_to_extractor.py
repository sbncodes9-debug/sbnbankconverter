#!/usr/bin/env python3
"""
Script to add OCR support to existing bank extractors
Usage: python add_ocr_to_extractor.py <extractor_file.py>
"""

import sys
import re

def add_ocr_to_extractor(file_path):
    """Add OCR support to an existing extractor file"""
    
    # Read the current file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if OCR is already added
    if 'ocr_helper' in content:
        print(f"OCR already added to {file_path}")
        return
    
    # Add OCR import after existing imports
    import_pattern = r'(from datetime import datetime\n)'
    ocr_import = r'''\1
# Import OCR helper (comment out if OCR not available)
try:
    from .ocr_helper import extract_text_hybrid, clean_ocr_text
    OCR_AVAILABLE = True
except ImportError:
    print("OCR not available - install pytesseract, Pillow, opencv-python")
    OCR_AVAILABLE = False

'''
    
    content = re.sub(import_pattern, ocr_import, content)
    
    # Find the main extraction function
    func_pattern = r'(def extract_\w+_data\(file_bytes\):.*?\n)(.*?)(with pdfplumber\.open\(BytesIO\(file_bytes\)\) as pdf:)'
    
    def replace_func(match):
        func_def = match.group(1)
        docstring_and_setup = match.group(2)
        pdf_open = match.group(3)
        
        # Add OCR logic before PDF processing
        ocr_logic = '''        # First try normal PDF text extraction
        normal_text_found = False
        
        ''' + pdf_open + '''
            total_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text and len(page_text.strip()) > 50:
                    normal_text_found = True
                    total_text += page_text + "\\n"
        
        # If normal extraction failed and OCR is available, use OCR
        if not normal_text_found and OCR_AVAILABLE:
            print("Normal PDF extraction insufficient, trying OCR...")
            ocr_text = extract_text_hybrid(file_bytes)
            if ocr_text:
                ocr_text = clean_ocr_text(ocr_text)
                total_text = ocr_text
                print(f"OCR extracted {len(ocr_text)} characters")
        
        # Process the extracted text (normal or OCR)
        if total_text:
            lines = total_text.split('\\n')
            # Continue with existing processing logic...
        
        # Original PDF processing (as fallback)
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:'''
        
        return func_def + docstring_and_setup + ocr_logic
    
    content = re.sub(func_pattern, replace_func, content, flags=re.DOTALL)
    
    # Write the modified content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"OCR support added to {file_path}")
    print("Note: You may need to manually adjust the text processing logic")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python add_ocr_to_extractor.py <extractor_file.py>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    add_ocr_to_extractor(file_path)