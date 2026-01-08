import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from io import BytesIO
import re


def preprocess_image_for_ocr(image):
    """
    Preprocess image to improve OCR accuracy
    """
    try:
        # Convert PIL image to OpenCV format
        img_array = np.array(image)
        if len(img_array.shape) == 3:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        else:
            img_cv = img_array
        
        # Convert to grayscale
        if len(img_cv.shape) == 3:
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_cv
        
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Convert back to PIL Image
        processed_image = Image.fromarray(thresh)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(processed_image)
        processed_image = enhancer.enhance(2.0)
        
        # Enhance sharpness
        processed_image = processed_image.filter(ImageFilter.SHARPEN)
        
        return processed_image
        
    except Exception as e:
        print(f"Image preprocessing error: {e}")
        return image  # Return original if preprocessing fails


def extract_text_with_ocr(file_bytes, use_preprocessing=True):
    """
    Extract text from PDF using OCR as fallback when normal text extraction fails
    
    Args:
        file_bytes: PDF file bytes
        use_preprocessing: Whether to preprocess images for better OCR
    
    Returns:
        str: Extracted text from all pages
    """
    all_text = ""
    
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                print(f"Processing page {page_num + 1} with OCR...")
                
                # First try normal text extraction
                page_text = page.extract_text()
                
                # If no text or very little text, use OCR
                if not page_text or len(page_text.strip()) < 50:
                    print(f"Page {page_num + 1}: Using OCR (little/no text found)")
                    
                    try:
                        # Convert page to image
                        page_image = page.to_image(resolution=300)  # High resolution for better OCR
                        pil_image = page_image.original
                        
                        # Preprocess image if requested
                        if use_preprocessing:
                            pil_image = preprocess_image_for_ocr(pil_image)
                        
                        # Perform OCR with custom config for financial documents
                        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,/-: ()'
                        ocr_text = pytesseract.image_to_string(pil_image, config=custom_config)
                        
                        if ocr_text.strip():
                            page_text = ocr_text
                            print(f"Page {page_num + 1}: OCR extracted {len(ocr_text)} characters")
                        else:
                            print(f"Page {page_num + 1}: OCR found no text")
                            
                    except Exception as e:
                        print(f"OCR error on page {page_num + 1}: {e}")
                        page_text = ""
                else:
                    print(f"Page {page_num + 1}: Using normal text extraction ({len(page_text)} characters)")
                
                if page_text:
                    all_text += page_text + "\n"
    
    except Exception as e:
        print(f"Error in OCR text extraction: {e}")
        return ""
    
    return all_text


def extract_text_hybrid(file_bytes):
    """
    Hybrid approach: Try normal extraction first, fallback to OCR if needed
    
    Args:
        file_bytes: PDF file bytes
    
    Returns:
        str: Extracted text using best available method
    """
    try:
        # First try normal pdfplumber extraction
        normal_text = ""
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    normal_text += page_text + "\n"
        
        # Check if normal extraction was successful
        if normal_text and len(normal_text.strip()) > 100:
            print("Using normal PDF text extraction")
            return normal_text
        else:
            print("Normal extraction insufficient, using OCR...")
            return extract_text_with_ocr(file_bytes)
            
    except Exception as e:
        print(f"Error in hybrid extraction: {e}")
        return ""


def clean_ocr_text(text):
    """
    Clean up common OCR errors in financial documents
    """
    if not text:
        return ""
    
    # Common OCR corrections for financial documents
    corrections = {
        # Date corrections
        r'\b(\d{1,2})[oO](\d{1,2})[oO](\d{4})\b': r'\1-\2-\3',  # 01o10o2025 -> 01-10-2025
        r'\b(\d{1,2})[il|](\d{1,2})[il|](\d{4})\b': r'\1-\2-\3',  # 01l10l2025 -> 01-10-2025
        
        # Amount corrections
        r'(\d+)[oO](\d{2})\b': r'\1.\2',  # 100o50 -> 100.50
        r'(\d+)[il|](\d{2})\b': r'\1.\2',  # 100l50 -> 100.50
        
        # Common character corrections
        r'\bO(\d)': r'0\1',  # O1 -> 01
        r'(\d)O\b': r'\g<1>0',  # 1O -> 10
        r'\bl(\d)': r'1\1',  # l1 -> 11
        r'(\d)l\b': r'\g<1>1',  # 1l -> 11
        
        # Remove extra spaces around numbers
        r'(\d)\s+(\d)': r'\1\2',
        
        # Fix common word errors
        r'\bDeposit\b': 'Deposit',
        r'\bWithdrawal\b': 'Withdrawal',
        r'\bBalance\b': 'Balance',
    }
    
    cleaned_text = text
    for pattern, replacement in corrections.items():
        cleaned_text = re.sub(pattern, replacement, cleaned_text)
    
    return cleaned_text


# Installation requirements (add to requirements.txt):
"""
pytesseract==0.3.10
Pillow==10.0.0
opencv-python==4.8.1.78
"""

# System requirements:
"""
For Windows:
1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install and add to PATH
3. Or set pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

For Linux:
sudo apt-get install tesseract-ocr

For Mac:
brew install tesseract
"""