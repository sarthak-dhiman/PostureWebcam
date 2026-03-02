# Placeholders — Must Replace Before Production

All values listed here are stubs/dev defaults that need real values before shipping.

---

## 1. Backend API Base URL

**File:** `core/constants.py` — line 10  
**Current value:**
```python
API_BASE = "http://127.0.0.1:8000/v1"
```
**Replace with:** Your production API base URL, e.g. `https://api.yourapp.com/v1`

---

## 2. Billing / Subscription Management URL

**File:** `core/constants.py` — line 18  
**Current value:**
```python
BILLING_URL = "https://app.yourdomain.com/settings/billing"
```
**Replace with:** Your real billing portal URL (e.g. Stripe Customer Portal, Paddle, etc.)  
**Also used in:** `views/account_page.py` line 332, `views/dashboard_page.py` line 455

---

## 3. Login Page Footer Links (Home / Privacy / Terms)

**File:** `views/login_page.py` — line 128  
**Current value:**
```python
'<a href="https://example.com">Posture Webcam</a> • <a href="https://example.com/privacy">Privacy</a> • <a href="https://example.com/terms">Terms</a>'
```
**Replace with:** Your real marketing site, privacy policy page, and terms of service page URLs.

---

## 4. Signup Page URL

**File:** `views/login_page.py` — line 121  
**Current value:**
```python
QDesktopServices.openUrl(QUrl("http://127.0.0.1:8000/v1/auth/signup"))
```
**Replace with:** Your production signup URL, e.g. `https://app.yourapp.com/signup`

---

## 5. SMTP Email Delivery — Docstring Example Credentials

**File:** `report_generator.py` — lines 10–11  
**Current value (in docstring):**
```python
send_email(pdf_path, "me@gmail.com", smtp_host="smtp.gmail.com",
           smtp_port=587, smtp_user="me@gmail.com", smtp_pass="app-pw")
```
**Replace with:** A real example using your support/no-reply address and SMTP provider details.

---

## 6. SMTP Default Host in Config

**File:** `report_generator.py` — line 1010 (`load_config` defaults)  
**Current value:**
```python
"smtp_host": "smtp.gmail.com",
"smtp_port": 587,
"smtp_user": "",
"smtp_pass": "",
```
If you use a transactional email provider (SendGrid, Mailgun, SES, etc.), update the defaults for `smtp_host` and `smtp_port` accordingly.

---

## 7. Mock API Demo Credentials *(dev-only — do not ship)*

**File:** `mock_api.py` — lines 21–22  
**Current value:**
```python
DEMO_EMAIL = "demo@local"
DEMO_PASS  = "demo1234"
```
`mock_api.py` must **not** be included in a production build. These credentials are for local development only.

---

## Summary Table

| # | File | What to replace | With |
|---|------|-----------------|------|
| 1 | `core/constants.py:10` | `API_BASE` URL | Production API base URL |
| 2 | `core/constants.py:18` | `BILLING_URL` | Real billing portal URL |
| 3 | `views/login_page.py:128` | Footer `example.com` links | Real site / privacy / terms URLs |
| 4 | `views/login_page.py:121` | Signup URL (`127.0.0.1`) | Production signup URL |
| 5 | `report_generator.py:10–11` | Docstring SMTP example | Real sender / SMTP details |
| 6 | `report_generator.py:1010` | SMTP default host/port | Your SMTP provider defaults |
| 7 | `mock_api.py:21–22` | Demo credentials | Remove file from production |
