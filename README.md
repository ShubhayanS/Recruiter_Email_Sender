# Recruiter Outreach Automation Suite

A full recruiter outreach workflow with:

- a browser UI for entering recruiters and sender/profile settings
- a generator script that creates recruiter email permutations
- a sender script that validates, sends, and monitors bounce behavior
- support for resume upload or resume path
- light and dark UI mode
- live backend log streaming in the web app

---

## What is included

This project currently consists of three main parts:

### 1. `email_pnc_generator.py`
This script generates realistic recruiter email permutations from:
- recruiter first name
- recruiter last name
- company name

It can run:
- interactively from terminal
- from a CSV in batch mode
- and optionally launch the sender script automatically

### 2. `email_validator_sender.py`
This script:
- loads generated recruiter email rows
- validates syntax, MX, disposable domains, and optional catch-all behavior
- sends one email at a time
- waits a random delay between sends
- monitors Gmail for bounce messages
- stores send history and recruiter history

### 3. Web app (`app.py` + `templates/index.html`)
This is the browser interface that:
- lets you add multiple recruiters with a plus button
- lets you enter Gmail, LinkedIn, GitHub, portfolio, phone, and name directly in the UI
- lets you upload a resume or use an existing resume path
- writes a `.env` file automatically for your backend scripts
- launches `email_pnc_generator.py` from the browser
- streams logs and job status in real time

---

## Project structure

A typical folder should look like this:

```text
Internship-finder-automation-tool/
├── app.py
├── templates/
│   └── index.html
├── uploads/
├── email_pnc_generator.py
├── email_validator_sender.py
├── requirements.txt
├── .env
├── myresume.pdf
├── sent_history.csv
├── sent_recruiter_history.csv
├── validation_results.csv
└── README.md
```

---

## Requirements

- Python 3.10+
- Gmail account with App Password enabled
- A resume file in PDF, DOC, or DOCX format

---

## Installation

### 1. Create and activate a virtual environment

Mac/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

If you are running just the scripts:

```bash
pip install dnspython requests tqdm python-dotenv
```

If you are also running the web interface:

```bash
pip install Flask python-dotenv dnspython requests tqdm
```

Or if you have a `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Gmail setup

You must use a Gmail App Password, not your normal Gmail password.

### Steps

1. Go to your Google Account security settings
2. Enable 2-Step Verification
3. Open App Passwords
4. Create an app password for Mail
5. Use that app password in the UI or `.env`

---

## Environment variables

Your backend sender script now expects values from a `.env` file.

### Correct `.env` format

Use this exact style:

```env
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password

YOUR_NAME=Shubhayan Saha
YOUR_PHONE=+1-XXX-XXX-XXXX
YOUR_LINKEDIN=https://www.linkedin.com/in/your-linkedin/
YOUR_GITHUB=https://github.com/your-github
YOUR_PORTFOLIO=https://your-portfolio.com

RESUME_PATH=myresume.pdf
```

### Important `.env` rules

Do this:

```env
KEY=value
```

Do not do this:

```env
KEY = "value"
```

The app and scripts expect:
- no spaces around `=`
- no quotes around values

---

## Security note

Your Gmail app password was exposed during debugging earlier. Revoke it and generate a new one before using this system again.

Also add this to `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.log
uploads/
sent_history.csv
sent_recruiter_history.csv
validation_results.csv
people_*.csv
```

---

# Backend scripts

## 1. Recruiter generator script

### Purpose
Generate likely recruiter email addresses from:
- first name
- last name
- company

### Interactive mode

```bash
python email_pnc_generator.py
```

You will be prompted for:
- Recruiter First Name
- Recruiter Last Name
- Company Name

Then the script:
- generates permutations
- saves them to a CSV
- optionally asks whether to run validation/sending now

### Batch mode

Prepare a CSV like this:

```csv
FirstName,LastName,Company
Alexander,Zlotnikov,Farmers Insurance
John,Doe,Google
Jane,Smith,Microsoft
```

Run:

```bash
python email_pnc_generator.py --input-csv people.csv
```

### Batch mode with auto-run

```bash
python email_pnc_generator.py --input-csv people.csv --auto-run --resume-path myresume.pdf
```

This will:
- generate recruiter emails for each person
- save output CSV files
- automatically launch `email_validator_sender.py`

---

## 2. Sender script

### Purpose
Take recruiter email rows and:
- validate them
- send messages one at a time
- attach your resume
- watch for bounces
- save results

### Basic usage

```bash
python email_validator_sender.py \
  --input recruiter_emails.csv \
  --send-application-emails \
  --resume-path myresume.pdf \
  --max-send 50 \
  --resume
```

### Important behavior
The sender script currently:
- sends sequentially, not in parallel
- waits a random delay after each email
- records successful sends to:
  - `sent_history.csv`
  - `sent_recruiter_history.csv`
- writes valid results to:
  - `validation_results.csv`

### Resume path priority
The sender script uses:

1. `--resume-path` if passed
2. `RESUME_PATH` from `.env`
3. otherwise it raises an error

---

## Sender profile fields used by the email template

The sender script reads these values:

- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `YOUR_NAME`
- `YOUR_PHONE`
- `YOUR_LINKEDIN`
- `YOUR_GITHUB`
- `YOUR_PORTFOLIO`
- `RESUME_PATH`

These values are used for:
- sender login
- email body template
- signature
- resume attachment source

---

## Email subject and template

### Subject format

```text
Interested in opportunity at <Company Name>
```

### Body includes
- personalized greeting
- your name
- interest in the company
- resume mention
- LinkedIn
- optional GitHub / portfolio depending on template version

---

# Web app

## What the UI does

The web app gives you a browser interface with two sections:

### Recruiters tab
- add recruiter rows
- each row contains:
  - first name
  - last name
  - company
- remove recruiter rows
- click “Send message” to launch the backend flow

### Profile Settings tab
Lets you enter all sender information directly in the UI instead of editing `.env` manually:

- Gmail address
- Gmail app password
- your name
- phone
- LinkedIn
- GitHub
- portfolio
- resume path
- resume upload

### Resume handling
The UI supports two options:

#### Option A: Upload resume
Upload a PDF/DOC/DOCX in the UI.  
The app saves it to the `uploads/` folder and uses that file.

#### Option B: Resume path
Provide an existing local path like:

```text
myresume.pdf
```

or

```text
/Users/yourname/Desktop/resume.pdf
```

If both are present, the uploaded file is typically used for that run.

---

## What happens when you click “Send message”

The web app does this:

1. collects recruiter rows from the form
2. collects your sender/profile settings
3. saves an uploaded resume if provided
4. writes a `.env` file for the backend
5. creates a temporary people CSV
6. launches:

```bash
python email_pnc_generator.py --input-csv <generated_people_csv> --auto-run --resume-path <resume>
```

7. the generator script then launches:
   - `email_validator_sender.py`
8. logs are streamed into the right-side panel in the UI

---

## Running the web app

### Start the server

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

### If port 5000 is busy
You may see:

```text
Address already in use
Port 5000 is in use by another program
```

#### Option 1: kill the process using port 5000

Find it:

```bash
lsof -i :5000
```

Kill it:

```bash
kill -9 <PID>
```

Or one-line version:

```bash
kill -9 $(lsof -ti :5000)
```

#### Option 2: use a different port
Edit the bottom of `app.py`:

```python
if __name__ == "__main__":
    app.run(debug=True, port=5001)
```

Then open:

```text
http://127.0.0.1:5001
```

#### Option 3: macOS AirPlay Receiver
On macOS, port conflicts can also happen because of AirPlay Receiver.

You can disable it in:
- System Settings
- General
- AirDrop & Handoff
- AirPlay Receiver → Off

---

## Frontend features

The UI currently includes:
- attractive glassmorphism-style layout
- light and dark mode toggle
- recruiter tab
- profile settings tab
- add/remove recruiter rows
- save profile locally in browser
- job status box
- live log viewer
- responsive layout for smaller screens

---

## Files created during runs

### `.env`
Written automatically by the web app from the Profile Settings tab.

### `people_<jobid>.csv`
Temporary people CSV created by the app for batch processing.

### `uploads/`
Stores uploaded resumes.

### `sent_history.csv`
Tracks emails that have already been sent.

### `sent_recruiter_history.csv`
Tracks recruiter send history with recruiter and company info.

### `validation_results.csv`
Stores final results for valid/no-bounce addresses.

---

## Common issues and fixes

### 1. `'NoneType' object has no attribute 'encode'`
This usually means your Gmail app password was not loaded correctly.

Most common causes:
- wrong `.env` variable name
- `.env` written in wrong format
- missing `GMAIL_APP_PASSWORD`

Correct key name:

```env
GMAIL_APP_PASSWORD=your_app_password
```

Not:

```env
APP_PASSWORD=...
```

---

### 2. Emails sent but history file has fewer rows
Possible causes:
- script was interrupted
- send succeeded but history write failed afterward
- terminal was suspended with `Ctrl + Z`

Gmail Sent folder is the real source of truth.  
The local CSV files are only your bookkeeping.

---

### 3. All emails go out at once
That happened in the earlier threaded version.

The current fixed sender should use sequential sending like this:

```python
for recruiter in send_candidates:
    success, status = send_application_email(...)
    time.sleep(random.randint(1, 50))
```

If you ever see bulk sending again, make sure you are not using `ThreadPoolExecutor` for the sending section.

---

### 4. Resume path missing
Fix by:
- uploading a resume in the UI
- or setting `RESUME_PATH` in `.env`
- or passing `--resume-path` directly

---

### 5. Flask says `render_template("index.html")` but page does not load
Make sure this file exists exactly here:

```text
templates/index.html
```

Flask requires the folder to be named `templates`.

---

### 6. Port 5000 already in use
See the troubleshooting section above.

---

## Suggested daily sending limits

To reduce Gmail rate-limit or spam risk:
- start with 10–20 sends/day
- gradually scale toward 30–50/day
- keep random delays between sends
- avoid very spammy wording
- avoid sending too many identical emails quickly

---

## Recommended improvements for later

Possible future upgrades:
- send progress bar in UI
- downloadable run report
- open/reply tracking
- multiple Gmail account support
- queue system for long jobs
- better persistence than in-memory Flask job store
- DB-backed recruiter history
- edit email template directly from the UI
- preview generated recruiter emails before sending
- login/authentication if this becomes multi-user

---

## Quick start summary

### Scripts only
```bash
source venv/bin/activate
pip install dnspython requests tqdm python-dotenv
python email_pnc_generator.py
```

### Web app
```bash
source venv/bin/activate
pip install Flask python-dotenv dnspython requests tqdm
python app.py
```

Then open:
```text
http://127.0.0.1:5000
```

---

## Final notes

This setup is best treated as a personal outreach automation workflow, not a bulk-email platform.

Use it carefully:
- keep credentials private
- revoke exposed app passwords
- send responsibly
- review templates regularly
- test with small batches first

