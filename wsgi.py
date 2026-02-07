"""
WSGI Configuration for PythonAnywhere Deployment

INSTRUCTIONS:
1. Upload this file to your PythonAnywhere account
2. In the Web tab, set the WSGI configuration file to point to this file
3. Update the 'project_home' path below with your actual username
4. Reload your web app

Example path: /home/yourusername/bank-statement-converter
"""

import sys
import os

# ============================================
# CHANGE THIS TO YOUR ACTUAL PATH
# ============================================
project_home = '/home/yourusername/bank-statement-converter'
# ============================================

# Add your project directory to the sys.path
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Set environment variables
os.environ['FLASK_ENV'] = 'production'

# Import Flask app
from app import app as application

# For debugging (remove in production)
# application.debug = False
