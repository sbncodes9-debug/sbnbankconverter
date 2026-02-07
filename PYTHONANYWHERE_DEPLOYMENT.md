# PythonAnywhere Deployment Guide

## Step 1: Sign Up for PythonAnywhere
1. Go to https://www.pythonanywhere.com/
2. Create a free account (or paid if you need more resources)
3. Verify your email

## Step 2: Upload Your Code

### Option A: Using Git (Recommended)
1. Push your code to GitHub/GitLab
2. In PythonAnywhere, open a Bash console
3. Clone your repository:
```bash
git clone https://github.com/yourusername/your-repo.git
cd your-repo
```

### Option B: Manual Upload
1. Go to "Files" tab in PythonAnywhere
2. Create a new directory (e.g., `bank-statement-converter`)
3. Upload all your files and folders:
   - app.py
   - requirements.txt
   - extractors/ folder
   - templates/ folder
   - static/ folder

## Step 3: Create Virtual Environment
1. Open a Bash console in PythonAnywhere
2. Navigate to your project directory:
```bash
cd ~/bank-statement-converter  # or your project folder name
```

3. Create virtual environment:
```bash
mkvirtualenv --python=/usr/bin/python3.10 myenv
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

## Step 4: Configure Web App
1. Go to "Web" tab in PythonAnywhere
2. Click "Add a new web app"
3. Choose "Manual configuration" (not Flask wizard)
4. Select Python 3.10

## Step 5: Configure WSGI File
1. In the Web tab, click on the WSGI configuration file link
2. Delete all content and replace with:

```python
import sys
import os

# Add your project directory to the sys.path
project_home = '/home/yourusername/bank-statement-converter'  # CHANGE THIS
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Set environment variables if needed
os.environ['FLASK_ENV'] = 'production'

# Import Flask app
from app import app as application
```

**IMPORTANT**: Replace `yourusername` with your actual PythonAnywhere username!

## Step 6: Configure Virtual Environment
1. In the Web tab, find "Virtualenv" section
2. Enter the path to your virtual environment:
```
/home/yourusername/.virtualenvs/myenv
```

## Step 7: Set Static Files (Optional but Recommended)
1. In the Web tab, scroll to "Static files" section
2. Add mapping:
   - URL: `/static/`
   - Directory: `/home/yourusername/bank-statement-converter/static`

## Step 8: Reload Web App
1. Scroll to top of Web tab
2. Click the big green "Reload" button
3. Your app should now be live at: `yourusername.pythonanywhere.com`

## Step 9: Test Your Application
1. Visit your URL: `https://yourusername.pythonanywhere.com`
2. Test each bank extractor
3. Test with password-protected PDFs
4. Test Excel conversion

## Troubleshooting

### Error Logs
- Check error logs in the Web tab under "Log files"
- Look at both error log and server log

### Common Issues

**1. Import Errors**
- Make sure virtual environment is activated
- Reinstall requirements: `pip install -r requirements.txt`

**2. File Not Found**
- Check all paths in WSGI file are correct
- Ensure all files uploaded properly

**3. Module Not Found**
- Verify virtual environment path is correct in Web tab
- Check that all dependencies installed

**4. 502 Bad Gateway**
- Check WSGI file syntax
- Look at error logs for details

**5. Static Files Not Loading**
- Verify static files mapping in Web tab
- Check CSS file path in templates

### Memory Issues (Free Account)
Free accounts have limited memory. If you hit limits:
- Upgrade to paid account
- Optimize code to use less memory
- Consider removing unused extractors

## Updating Your App
When you make changes:

### If using Git:
```bash
cd ~/bank-statement-converter
git pull origin main
```

### If manual upload:
- Upload changed files through Files tab

Then:
1. Go to Web tab
2. Click "Reload" button

## Security Notes
1. Never commit passwords or secrets to Git
2. Use environment variables for sensitive data
3. Consider adding authentication for production use
4. Keep dependencies updated

## Free Account Limitations
- Limited CPU time per day
- Limited storage
- App sleeps after inactivity
- One web app only

Consider upgrading if you need:
- More CPU time
- Multiple apps
- Custom domains
- More storage

## Support
- PythonAnywhere Forums: https://www.pythonanywhere.com/forums/
- PythonAnywhere Help: https://help.pythonanywhere.com/
