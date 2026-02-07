# Quick Start Guide - PythonAnywhere Deployment

## 🚀 Fast Deployment (5 Minutes)

### 1. Create Account
- Go to https://www.pythonanywhere.com/
- Sign up (free account works)

### 2. Upload Code
**Bash Console:**
```bash
# If using Git
git clone YOUR_REPO_URL
cd bank-statement-converter

# Or manually upload files via Files tab
```

### 3. Install Dependencies
```bash
# Create virtual environment
mkvirtualenv --python=/usr/bin/python3.10 myenv

# Install packages
pip install -r requirements.txt
```

### 4. Create Web App
- Go to **Web** tab
- Click **Add a new web app**
- Choose **Manual configuration**
- Select **Python 3.10**

### 5. Configure WSGI
- Click on WSGI configuration file
- Replace content with `wsgi.py` file content
- **IMPORTANT**: Change `yourusername` to your actual username!

### 6. Set Virtual Environment
- In Web tab, find **Virtualenv** section
- Enter: `/home/yourusername/.virtualenvs/myenv`

### 7. Reload & Test
- Click green **Reload** button
- Visit: `https://yourusername.pythonanywhere.com`

## ✅ Done!

Your bank statement converter is now live!

## 📝 Quick Commands Reference

```bash
# Navigate to project
cd ~/bank-statement-converter

# Activate virtual environment
workon myenv

# Update code (if using Git)
git pull

# Install new packages
pip install package-name

# Check logs
tail -f /var/log/yourusername.pythonanywhere.com.error.log
```

## 🔧 After Changes
1. Make your code changes
2. Upload/pull changes
3. Go to Web tab
4. Click **Reload**

## 📚 Full Guide
See `PYTHONANYWHERE_DEPLOYMENT.md` for detailed instructions and troubleshooting.
