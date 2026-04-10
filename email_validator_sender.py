# Optional additional info in email signature:
#   {YOUR_PHONE}<br>
#   LinkedIn: <a href="{YOUR_LINKEDIN}">{YOUR_LINKEDIN}</a><br>
#   GitHub: <a href="{YOUR_GITHUB}">{YOUR_GITHUB}</a>
#   {portfolio_html}

from dotenv import load_dotenv
load_dotenv(override=True)



import re
import dns.resolver
import requests
import smtplib
import imaplib
import email
import argparse
import logging
import csv
import os
import sys
import time
import random
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from email.message import EmailMessage
from tqdm import tqdm
from typing import Dict, Set, List, Tuple

# ================================================
# EMAIL SENDER + VALIDATOR + BOUNCE CHECKER
# ================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        # logging.FileHandler(f"email_validator_{datetime.now().strftime('%Y%m%d_%H%M')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)



# ========================== CONFIG ==========================
DISPOSABLE_BLOCKLIST_URL = "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf"

COMMON_TYPO_DOMAINS = {
    "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmai.com": "gmail.com",
    "yaho.com": "yahoo.com", "yahho.com": "yahoo.com",
    "hotmai.com": "hotmail.com", "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com",
}

# ========================== YOUR EMAIL PROFILE ==========================
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD")

YOUR_NAME = os.getenv("YOUR_NAME", "Your Name")
YOUR_PHONE = os.getenv("YOUR_PHONE", "")
YOUR_LINKEDIN = os.getenv("YOUR_LINKEDIN", "")
YOUR_PORTFOLIO = os.getenv("YOUR_PORTFOLIO", "")

DEFAULT_RESUME_PATH = os.getenv("RESUME_PATH")

print("Sending from:", GMAIL_ADDRESS)
logger.info(f"Using Gmail account from env: {GMAIL_ADDRESS}")

# ========================== DATA MODEL ==========================
@dataclass
class RecruiterRow:
    email: str
    first_name: str
    last_name: str
    company_name: str
    company_domain: str
    created_at: str


# ========================== HELPERS ==========================

def load_emails(input_str: str) -> List[str]:
    if os.path.exists(input_str) and input_str.endswith(('.txt', '.csv')):
        with open(input_str, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and '@' in line]
    return [e.strip() for e in input_str.split(',') if e.strip() and '@' in e]


def load_recruiter_rows(csv_file: str) -> List[RecruiterRow]:
    rows: List[RecruiterRow] = []

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if not row:
                continue

            # Skip header if present
            if i == 1 and row[0].strip().lower() in {"email", "email_address"}:
                continue

            if len(row) < 6:
                logger.warning(f"Skipping row {i}: expected 6 columns, got {len(row)}")
                continue

            email_addr = row[0].strip()
            first_name = row[1].strip()
            last_name = row[2].strip()
            company_name = row[3].strip()
            company_domain = row[4].strip()
            created_at = row[5].strip()

            if not validate_syntax(email_addr):
                logger.warning(f"Skipping row {i}: invalid email syntax -> {email_addr}")
                continue

            rows.append(
                RecruiterRow(
                    email=email_addr,
                    first_name=first_name,
                    last_name=last_name,
                    company_name=company_name,
                    company_domain=company_domain,
                    created_at=created_at,
                )
            )

    return rows


def load_sent_history(history_file: str = "sent_history.csv") -> Set[str]:
    if not os.path.exists(history_file):
        return set()
    sent = set()
    with open(history_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row and len(row) > 0:
                sent.add(row[0].strip())
    return sent


def save_sent_history(email_address: str, history_file: str = "sent_history.csv"):
    exists = os.path.exists(history_file)
    with open(history_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(['Email', 'SentAt'])
        writer.writerow([email_address, datetime.now().isoformat()])


def save_sent_recruiter_history(recruiter: RecruiterRow, history_file: str = "sent_recruiter_history.csv"):
    exists = os.path.exists(history_file)
    with open(history_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["Email", "FirstName", "LastName", "Company", "SentAt"])
        writer.writerow([
            recruiter.email,
            recruiter.first_name,
            recruiter.last_name,
            recruiter.company_name,
            datetime.now().isoformat()
        ])


def validate_syntax(email_str: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_str))


def is_disposable(domain: str) -> bool:
    domain = domain.lower()
    try:
        resp = requests.get(DISPOSABLE_BLOCKLIST_URL, timeout=10)
        if resp.status_code == 200:
            block = {ln.strip().lower() for ln in resp.text.splitlines() if ln.strip() and not ln.startswith('#')}
            if domain in block:
                return True
    except Exception:
        pass
    common = {
        "10minutemail.com", "tempmail.org", "guerrillamail.com", "mailinator.com",
        "yopmail.com", "dispostable.com", "trashmail.com", "temp-mail.org",
        "sharklasers.com", "grr.la"
    }
    return domain in common


def has_mx_records(domain: str) -> bool:
    try:
        return len(dns.resolver.resolve(domain, 'MX', lifetime=8)) > 0
    except Exception:
        return False


def detect_typo_domain(domain: str) -> str:
    return COMMON_TYPO_DOMAINS.get(domain.lower(), "")


def probe_catch_all(domain: str, sender_email: str, app_pw: str) -> bool:
    if domain.endswith('.gmail.com') or domain in {"yahoo.com", "hotmail.com", "outlook.com", "aol.com", "protonmail.com"}:
        return False
    try:
        s = smtplib.SMTP('smtp.gmail.com', 587, timeout=12)
        s.starttls()
        s.login(sender_email, app_pw)
        s.mail(f"probe@{sender_email.split('@')[1]}")
        code, _ = s.rcpt(f"random{random.randint(10000,999999)}@{domain}")
        s.quit()
        return code == 250
    except Exception:
        return False


def get_body_snippet(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                try:
                    return part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except Exception:
                    return ""
    else:
        try:
            return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except Exception:
            return ""
    return ""


def is_strong_bounce(msg) -> bool:
    subject = (msg.get('subject') or '').lower()
    from_ = (msg.get('from') or '').lower()
    body = get_body_snippet(msg).lower()

    is_daemon = 'mailer-daemon' in from_ or 'postmaster' in from_ or 'gsmtp' in body

    hard_keywords = [
        '550 5.1.1', '550 5.1.0', '550 5.2.1', 'address not found',
        "address couldn't be found",
        'the email account that you tried to reach does not exist',
        'no such user', 'does not exist', 'invalid recipient',
        'recipient address rejected', 'delivery has failed', 'undeliverable',
        'delivery status notification', 'message blocked'
    ]

    has_hard = any(kw in body for kw in hard_keywords) or any(
        kw in subject for kw in ['undeliverable', 'failure', 'delivery status notification']
    )
    has_5xx = any(code in body for code in ['550', '551', '552', '553', '554', '5.1.1', '5.1.0', '5.2.1'])

    return is_daemon or has_hard or has_5xx


def extract_recipient_from_bounce(msg, candidates: Set[str]) -> str | None:
    body = get_body_snippet(msg)
    body_lower = body.lower()

    patterns = [
        r'550 5\.1\.1.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'your message wasn\'t delivered to\s+([^\s<]+@[^\s>]+)',
        r'address not found.*?([^\s<]+@[^\s>]+)',
        r'the email account that you tried to reach does not exist.*?([^\s<]+@[^\s>]+)',
        r'to\s+([^\s<]+@[^\s>]+)',
        r'final-recipient:.*?rfc822;\s*([^\s<]+@[^\s>]+)',
        r'original-recipient:.*?rfc822;\s*([^\s<]+@[^\s>]+)',
    ]

    for pat in patterns:
        m = re.search(pat, body_lower, re.IGNORECASE | re.DOTALL)
        if m:
            found = m.group(1).strip().lower()
            for cand in candidates:
                if cand.lower() == found:
                    return cand

    for cand in candidates:
        if cand.lower() in body_lower and any(
            x in body_lower for x in ['550 5.1.1', 'address not found', 'does not exist', 'undeliverable']
        ):
            return cand
    return None


def build_subject(company_name: str) -> str:
    return f"Interested in opportunity at {company_name}"


def build_email_body_text(first_name: str, company_name: str) -> str:
    greeting_name = first_name if first_name else "Hiring Team"
    portfolio_line = f"Portfolio: {YOUR_PORTFOLIO}\n" if YOUR_PORTFOLIO else ""

    return f"""Hi {greeting_name},

I hope you are doing well.

My name is {YOUR_NAME}, and I am reaching out to express my interest in potential opportunity at {company_name}. I come from a background in data and software development, and I came across an opportunity that I believe aligns with my interests and experience.

I have attached my resume for your review. I would be grateful to connect and talk more about how I can be a great fit for the role and understand the hiring process.

Thank you for your time and consideration.

Best regards,
{YOUR_NAME}
LinkedIn: {YOUR_LINKEDIN}
{portfolio_line}"""


def build_email_body_html(first_name: str, company_name: str) -> str:
    greeting_name = first_name if first_name else "Hiring Team"

    portfolio_html = (
        f'<br>Portfolio: <a href="{YOUR_PORTFOLIO}">{YOUR_PORTFOLIO}</a>'
        if YOUR_PORTFOLIO else ""
    )

    return f"""
    <html>
      <body>
        <p>Hi {greeting_name},</p>

        <p>I hope you are doing well.</p>

        <p>
          My name is <strong>{YOUR_NAME}</strong>, and I am reaching out to express my interest in
          a potential opportunity at <strong>{company_name}</strong>. I come from a background in
          data engineering, data science, and software development, and I would love talk more about my passion,
          understand the hiring process and how I can be a great fit for the role.
        </p>

        <p>
          I have attached my resume for your review. I would be grateful if you can provide me sometime in your schedule.
        </p>

        <p>Thank you again for your time and consideration. I will be looking forward to hearing from you.</p>

        <p>
          Best regards,<br>
          <strong>{YOUR_NAME}</strong><br>
          LinkedIn: <a href="{YOUR_LINKEDIN}">{YOUR_LINKEDIN}</a><br>
          {portfolio_html}
        </p>
      </body>
    </html>
    """


def attach_file(msg: EmailMessage, file_path: str):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Attachment not found: {file_path}")

    with open(path, "rb") as f:
        data = f.read()

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        maintype, subtype = "application", "pdf"
    elif suffix in {".doc", ".docx"}:
        maintype, subtype = "application", "octet-stream"
    else:
        maintype, subtype = "application", "octet-stream"

    msg.add_attachment(
        data,
        maintype=maintype,
        subtype=subtype,
        filename=path.name
    )


def send_application_email(
    sender: str,
    app_pw: str,
    recruiter: RecruiterRow,
    resume_path: str,
    test_id: int = 0
) -> Tuple[bool, str]:
    subject = build_subject(recruiter.company_name)
    text_body = build_email_body_text(recruiter.first_name, recruiter.company_name)
    html_body = build_email_body_html(recruiter.first_name, recruiter.company_name)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recruiter.email
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    attach_file(msg, resume_path)

    for attempt in range(1, 4):
        try:
            srv = smtplib.SMTP('smtp.gmail.com', 587, timeout=20)
            srv.starttls()
            srv.login(sender, app_pw)
            srv.mail(sender)

            code, response = srv.rcpt(recruiter.email)
            if code >= 400:
                srv.quit()
                response_text = response.decode(errors='ignore') if isinstance(response, bytes) else str(response)
                return False, f"REJECTED (SMTP {code}): {response_text[:200]}"

            srv.send_message(msg)
            srv.quit()
            return True, "Sent successfully"

        except smtplib.SMTPRecipientsRefused:
            return False, "REJECTED (SMTP Recipients Refused)"
        except Exception as e:
            if attempt == 3:
                return False, f"Send failed: {str(e)[:250]}"
            time.sleep(attempt * random.uniform(3, 7))

    return False, "Unknown send failure"


def monitor_bounces(sender: str, app_pw: str, sent_emails: Set[str], start_time: datetime, timeout_min: int = 12) -> Dict[str, str]:
    logger.info(f"Starting bounce monitoring — {len(sent_emails)} emails (max {timeout_min} min)")
    remaining = sent_emails.copy()
    results: Dict[str, str] = {}
    end_time = start_time + timedelta(minutes=timeout_min)

    folders = ['INBOX', '"[Gmail]/All Mail"', '"[Gmail]/Spam"', '"[Gmail]/Trash"']

    while datetime.now() < end_time and remaining:
        try:
            m = imaplib.IMAP4_SSL('imap.gmail.com')
            m.login(sender, app_pw)

            for folder in folders:
                try:
                    m.select(folder, readonly=True)
                except Exception:
                    continue

                since_str = (start_time - timedelta(hours=12)).strftime("%d-%b-%Y")
                _, data = m.search(None, f'(SINCE {since_str})')

                if not data or not data[0]:
                    continue

                msg_nums = data[0].split()[-800:]

                for num in msg_nums:
                    try:
                        _, raw = m.fetch(num, '(RFC822)')
                        if not raw or not raw[0]:
                            continue
                        msg = email.message_from_bytes(raw[0][1])

                        if is_strong_bounce(msg):
                            victim = extract_recipient_from_bounce(msg, remaining)
                            if victim:
                                logger.warning(f"BOUNCE DETECTED in {folder} -> {victim}")
                                results[victim] = "BOUNCED"
                                remaining.discard(victim)
                    except Exception:
                        continue

            m.logout()

            elapsed_min = (datetime.now() - start_time).total_seconds() / 60
            sleep_time = 8 if elapsed_min < 8 else 25
            time.sleep(sleep_time + random.uniform(0, 5))

        except Exception as e:
            logger.error(f"IMAP error: {e}")
            time.sleep(15)

    for addr in remaining:
        results[addr] = "No bounce detected (likely valid)"

    logger.info(f"Monitoring finished. Bounces found: {sum(1 for v in results.values() if v == 'BOUNCED')}")
    return results


def save_results_to_csv(results: Dict[str, str], validation: Dict[str, str], filename: str = "validation_results.csv"):
    valid_emails = []
    for email_address, status in results.items():
        if status == "No bounce detected (likely valid)":
            valid_emails.append({
                'Email': email_address,
                'Status': 'VALID',
                'Details': validation.get(email_address, 'Domain valid'),
                'Timestamp': datetime.now().isoformat()
            })

    if valid_emails:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Email', 'Status', 'Details', 'Timestamp'])
            writer.writeheader()
            writer.writerows(valid_emails)
        logger.info(f"Saved {len(valid_emails)} VALID emails to {filename}")
    else:
        logger.info("No valid emails found.")


# ========================== MAIN ==========================

def main():
    parser = argparse.ArgumentParser(description="Email Sender + Validator")
    parser.add_argument("--input", required=True, help="CSV file with recruiter rows")
    parser.add_argument("--max-send", type=int, default=400)
    parser.add_argument("--workers", type=int, default=4)  # kept for compatibility, no longer used for sending
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-catchall-probe", action="store_true")
    parser.add_argument("--timeout-min", type=int, default=12)
    parser.add_argument("--resume-path", required=False, help="Path to your resume PDF/DOC/DOCX")
    parser.add_argument("--send-application-emails", action="store_true")
    args = parser.parse_args()

    logger.info("=== EMAIL SENDER START ===")

    history_file = "sent_history.csv"
    already_sent = load_sent_history(history_file) if args.resume else set()

    validation: Dict[str, str] = {}

    if args.send_application_emails:
        if not args.resume_path:
            logger.error("--resume-path is required when --send-application-emails is used")
            sys.exit(1)

        recruiters = load_recruiter_rows(args.input)
        logger.info(f"Loaded {len(recruiters)} recruiter rows | Already sent: {len(already_sent)}")

        send_candidates: List[RecruiterRow] = []

        for recruiter in tqdm(recruiters, desc="Validating"):
            domain = recruiter.email.split('@', 1)[1].lower()

            if not validate_syntax(recruiter.email):
                validation[recruiter.email] = "Invalid syntax"
                continue

            typo_fix = detect_typo_domain(domain)
            if typo_fix:
                validation[recruiter.email] = f"Typo domain ({domain} -> {typo_fix})"
                continue

            if is_disposable(domain):
                validation[recruiter.email] = "Disposable"
                continue

            if not has_mx_records(domain):
                validation[recruiter.email] = "No MX"
                continue

            validation[recruiter.email] = "Domain valid"
            send_candidates.append(recruiter)

            if not args.no_catchall_probe:
                if probe_catch_all(domain, GMAIL_ADDRESS, APP_PASSWORD):
                    validation[recruiter.email] += " (catch-all likely)"

        send_candidates = [r for r in send_candidates if r.email not in already_sent][:args.max_send]
        logger.info(f"Ready to send application emails: {len(send_candidates)}")

        if args.validate_only or not send_candidates:
            logger.info("Validation-only mode or no emails to send.")
            return

        send_start = datetime.now()
        sent_ok: List[str] = []
        immediate_rejects: Dict[str, str] = {}

        # Sequential sending: one email at a time with random delay
        counter = 1
        for recruiter in tqdm(send_candidates, desc="Sending"):
            try:
                resume_path = args.resume_path or DEFAULT_RESUME_PATH

                if not resume_path:
                    raise ValueError("❌ Resume path missing. Provide --resume-path or set RESUME_PATH in .env")

                success, status = send_application_email(
                    GMAIL_ADDRESS,
                    APP_PASSWORD,
                    recruiter,
                    resume_path,
                    counter
                )

                if success:
                    sent_ok.append(recruiter.email)
                    save_sent_history(recruiter.email, history_file)
                    save_sent_recruiter_history(recruiter, "sent_recruiter_history.csv")
                    logger.info(f"Sent successfully -> {recruiter.email}")
                else:
                    immediate_rejects[recruiter.email] = status
                    logger.warning(f"Failed to send -> {recruiter.email} | {status}")

            except Exception as e:
                immediate_rejects[recruiter.email] = f"Send error: {str(e)[:250]}"
                logger.exception(f"Unexpected send error -> {recruiter.email}")

            counter += 1

            delay = random.randint(1, 50)
            logger.info(f"Sleeping for {delay} seconds before next email...")
            time.sleep(delay)

        final_results: Dict[str, str] = dict(immediate_rejects)

        if sent_ok:
            logger.info("Waiting 90 seconds for initial bounces...")
            time.sleep(90)
            bounce_dict = monitor_bounces(
                GMAIL_ADDRESS,
                APP_PASSWORD,
                set(sent_ok),
                send_start,
                timeout_min=args.timeout_min
            )
            final_results.update(bounce_dict)

        logger.info("\n" + "═" * 110)
        logger.info("FINAL EMAIL SEND RESULT")
        logger.info("═" * 110)

        valid_count = 0
        bounced_count = 0
        failed_count = 0

        print(f"{'Email Address':<45} {'Company':<30} {'Validation':<30} {'Final Status':<25}")
        print("-" * 135)

        for recruiter in recruiters:
            email_addr = recruiter.email
            val = validation.get(email_addr, "—")
            res = final_results.get(email_addr, "Not sent")

            if res == "No bounce detected (likely valid)":
                status = "✅ SENT / NO BOUNCE"
                valid_count += 1
            elif "BOUNCED" in res or "REJECTED" in res:
                status = "❌ FAILED / BOUNCED"
                bounced_count += 1
            elif "Send failed" in res or "Send error" in res:
                status = "⚠️ SEND FAILED"
                failed_count += 1
            else:
                status = "⚠️ UNKNOWN / NOT SENT"

            print(f"{email_addr:<45} {recruiter.company_name[:28]:<30} {val[:28]:<30} {status:<25}")
            logger.info(f"{email_addr:<45} {recruiter.company_name[:28]:<30} {val[:28]:<30} {status}")

        print("-" * 135)
        print(
            f"Total Sent/No Bounce: {valid_count} | "
            f"Total Failed/Bounced: {bounced_count} | "
            f"Total Send Errors: {failed_count} | "
            f"Total Processed: {len(recruiters)}"
        )

        logger.info(
            f"Summary -> Sent/No Bounce: {valid_count} | Failed/Bounced: {bounced_count} | "
            f"Send Errors: {failed_count} | Total Processed: {len(recruiters)}"
        )

        save_results_to_csv(final_results, validation)
        logger.info("Process completed successfully.")
        return

    # Fallback to old email-only flow if user does not use recruiter mode
    emails = load_emails(args.input)
    logger.info(f"Loaded {len(emails)} emails | Already sent: {len(already_sent)}")

    to_send_candidates: List[str] = []

    for e in tqdm(emails, desc="Validating"):
        if not validate_syntax(e):
            validation[e] = "Invalid syntax"
            continue

        domain = e.split('@', 1)[1].lower()

        if detect_typo_domain(domain):
            validation[e] = f"Typo domain ({domain})"
            continue

        if is_disposable(domain):
            validation[e] = "Disposable"
            continue

        if not has_mx_records(domain):
            validation[e] = "No MX"
            continue

        validation[e] = "Domain valid"
        to_send_candidates.append(e)

        if not args.no_catchall_probe:
            if probe_catch_all(domain, GMAIL_ADDRESS, APP_PASSWORD):
                validation[e] += " (catch-all likely)"

    logger.info("Old non-recruiter mode loaded. Use --send-application-emails for recruiter CSV flow.")


if __name__ == "__main__":
    main()