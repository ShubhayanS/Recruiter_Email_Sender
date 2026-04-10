from dotenv import load_dotenv
load_dotenv(override=True)

import re
import csv
import os
import sys
import shlex
import argparse
from pathlib import Path
from datetime import datetime
import logging
from typing import List, Set

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

SENDER_SCRIPT = "email_validator_sender.py"
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


def clean_name(name: str) -> str:
    return re.sub(r'[^a-zA-Z]', '', name.lower().strip())


def generate_email_permutations(first: str, last: str, domain: str) -> List[str]:
    f = clean_name(first)
    l = clean_name(last)
    if not f or not l:
        return []

    fi = f[0]
    li = l[0]

    separators = ['', '.', '-', '_']
    emails: Set[str] = set()

    for sep in separators:
        emails.add(f"{f}{sep}{l}@{domain}")
        emails.add(f"{l}{sep}{f}@{domain}")
        emails.add(f"{fi}{sep}{l}@{domain}")
        emails.add(f"{l}{sep}{fi}@{domain}")
        emails.add(f"{f}{sep}{li}@{domain}")
        emails.add(f"{li}{sep}{f}@{domain}")

    emails.add(f"{f}{l}@{domain}")
    emails.add(f"{l}{f}@{domain}")
    emails.add(f"{fi}{l}@{domain}")
    emails.add(f"{l}{fi}@{domain}")
    emails.add(f"{f}{li}@{domain}")
    emails.add(f"{li}{f}@{domain}")

    emails.add(f"{f}@{domain}")
    emails.add(f"{l}@{domain}")

    extras = [
        f"{f}.{l}@{domain}", f"{l}.{f}@{domain}",
        f"{f}{l[0:3]}@{domain}", f"{l}{f[0:3]}@{domain}",
        f"{f[0:3]}{l}@{domain}", f"{l[0:3]}{f}@{domain}",
        f"{fi}{li}{l}@{domain}", f"{li}{fi}{f}@{domain}",
        f"{f}_{l}@{domain}", f"{l}_{f}@{domain}",
        f"{f}-{l}@{domain}", f"{l}-{f}@{domain}",
        f"{f}.{li}@{domain}", f"{li}.{f}@{domain}",
    ]
    emails.update(extras)

    return sorted(list(emails))


def find_company_domain(company_name: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower().strip())
    return f"{base}.com"


def save_generated_csv(possible_emails: List[str], first: str, last: str, company: str, domain: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TEMP_DIR / f"recruiter_emails_{clean_name(first)}_{clean_name(last)}_{timestamp}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Email', 'FirstName', 'LastName', 'Company', 'Domain', 'GeneratedAt'])
        now_iso = datetime.now().isoformat()
        for email in possible_emails:
            writer.writerow([email, first, last, company, domain, now_iso])

    return filename


def launch_sender(csv_file: Path, resume_path: str, max_send: int):
    if not os.path.exists(SENDER_SCRIPT):
        print(f"❌ Sender script not found: {SENDER_SCRIPT}")
        sys.exit(1)

    if not csv_file.exists():
        print(f"❌ Input CSV not found: {csv_file}")
        sys.exit(1)

    if not resume_path:
        print("❌ Resume path is required to start sender.")
        sys.exit(1)

    if not os.path.exists(resume_path):
        print(f"❌ Resume file not found: {resume_path}")
        sys.exit(1)

    cmd = [
        sys.executable,
        SENDER_SCRIPT,
        "--input", str(csv_file),
        "--send-application-emails",
        "--resume-path", resume_path,
        "--max-send", str(max_send),
        "--resume",
    ]

    pretty_cmd = " ".join(shlex.quote(part) for part in cmd)

    print("\n🚀 Starting email sender...")
    print(pretty_cmd)
    exit_code = os.system(pretty_cmd)

    if exit_code == 0:
        print("✅ Email sender finished! Check result/ for final report")
    else:
        print(f"⚠️ Email sender failed with exit code: {exit_code}")
        sys.exit(1)


def process_person(first: str, last: str, company: str, auto_run: bool = False, resume_path: str = ""):
    if not first or not last or not company:
        print("❌ All fields required!")
        return

    domain = find_company_domain(company)
    print(f"\n🔍 Company domain detected → {domain}")

    possible_emails = generate_email_permutations(first, last, domain)

    print(f"\n✅ Generated {len(possible_emails)} realistic email permutations for {first} {last}:\n")
    for email in possible_emails:
        print(f"   • {email}")

    filename = save_generated_csv(possible_emails, first, last, company, domain)
    print(f"\n💾 Temporary recruiter CSV saved to → {filename}")

    should_run = auto_run
    if not auto_run:
        should_run = input("\nRun validation on these emails now? (y/n): ").strip().lower() == 'y'

    if should_run:
        if not resume_path:
            resume_path = input("Resume path (e.g. myresume.pdf): ").strip()

        try:
            launch_sender(
                csv_file=filename,
                resume_path=resume_path,
                max_send=len(possible_emails),
            )
        finally:
            try:
                if filename.exists():
                    filename.unlink()
                    print(f"🧹 Deleted temporary file → {filename}")
            except Exception as cleanup_err:
                print(f"⚠️ Could not delete temp file {filename}: {cleanup_err}")


def process_batch_csv(input_csv: str, auto_run: bool = False, resume_path: str = ""):
    if not os.path.exists(input_csv):
        print(f"❌ CSV file not found: {input_csv}")
        return

    with open(input_csv, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)

        required_cols = {"FirstName", "LastName", "Company"}
        if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
            print("❌ CSV must contain headers: FirstName, LastName, Company")
            return

        rows = list(reader)
        if not rows:
            print("❌ CSV has no data rows.")
            return

        print(f"\n📄 Loaded {len(rows)} people from {input_csv}")

        for idx, row in enumerate(rows, start=1):
            first = (row.get("FirstName") or "").strip()
            last = (row.get("LastName") or "").strip()
            company = (row.get("Company") or "").strip()

            print("\n" + "=" * 70)
            print(f"Processing {idx}/{len(rows)}: {first} {last} | {company}")
            print("=" * 70)

            process_person(
                first=first,
                last=last,
                company=company,
                auto_run=auto_run,
                resume_path=resume_path,
            )


def main():
    parser = argparse.ArgumentParser(description="Recruiter Email Generator")
    parser.add_argument("--input-csv", help="Optional CSV with headers: FirstName, LastName, Company")
    parser.add_argument("--resume-path", help="Optional resume path for auto-run mode")
    parser.add_argument("--auto-run", action="store_true", help="Automatically launch sender after generating CSV(s)")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("RECRUITER EMAIL GENERATOR — EXHAUSTIVE PERMUTATIONS")
    print("=" * 70)

    if args.input_csv:
        process_batch_csv(
            input_csv=args.input_csv,
            auto_run=args.auto_run,
            resume_path=args.resume_path or "",
        )
        print("\n🎯 Batch processing done!")
        return

    first = input("Recruiter First Name : ").strip()
    last = input("Recruiter Last Name  : ").strip()
    company = input("Company Name         : ").strip()

    process_person(
        first=first,
        last=last,
        company=company,
        auto_run=False,
        resume_path=args.resume_path or "",
    )

    print("\n🎯 Done! Good luck with your outreach.")


if __name__ == "__main__":
    main()