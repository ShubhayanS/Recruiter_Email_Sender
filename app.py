from flask import Flask, request, jsonify, render_template
import subprocess
import threading
import json
import uuid
import csv
import sys
from pathlib import Path
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

PROFILE_JSON = DATA_DIR / "profile.json"
ENV_FILE = BASE_DIR / ".env"

jobs = {}

def load_saved_profile():
    if PROFILE_JSON.exists():
        try:
            return json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_profile_json(profile: dict):
    PROFILE_JSON.write_text(json.dumps(profile, indent=2), encoding="utf-8")

def write_env(profile: dict):
    lines = [
        f"GMAIL_ADDRESS={profile.get('gmail_address', '')}",
        f"GMAIL_APP_PASSWORD={profile.get('gmail_app_password', '')}",
        f"YOUR_NAME={profile.get('your_name', '')}",
        f"YOUR_PHONE={profile.get('your_phone', '')}",
        f"YOUR_LINKEDIN={profile.get('your_linkedin', '')}",
        f"YOUR_GITHUB={profile.get('your_github', '')}",
        f"YOUR_PORTFOLIO={profile.get('your_portfolio', '')}",
        f"RESUME_PATH={profile.get('resume_path', '')}",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def create_csv(recruiters, job_id):
    file_path = DATA_DIR / f"people_{job_id}.csv"
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["FirstName", "LastName", "Company"])
        for r in recruiters:
            writer.writerow([r["firstName"], r["lastName"], r["company"]])
    return file_path

def append_log(job_id, message):
    jobs[job_id]["logs"] += message
    log_file = LOG_DIR / f"job_{job_id}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message)
    jobs[job_id]["log_file"] = str(log_file)

def run_job(job_id, recruiters):
    jobs[job_id]["status"] = "running"
    try:
        profile = load_saved_profile()

        resume_path = (profile.get("resume_path") or "").strip()
        append_log(job_id, f"Using resume path from saved profile: {resume_path}\n")

        if not resume_path:
            raise ValueError("Resume path or upload is required. Save your profile with a resume first.")

        if not Path(resume_path).exists():
            raise FileNotFoundError(f"Saved resume path does not exist: {resume_path}")

        write_env(profile)
        append_log(job_id, "Wrote .env file successfully.\n")

        csv_file = create_csv(recruiters, job_id)
        append_log(job_id, f"Created recruiter CSV: {csv_file}\n")

        cmd = [
            sys.executable,
            str(BASE_DIR / "email_pnc_generator.py"),
            "--input-csv",
            str(csv_file),
            "--auto-run",
            "--resume-path",
            resume_path
        ]

        append_log(job_id, "Running command:\n")
        append_log(job_id, " ".join(cmd) + "\n\n")

        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                append_log(job_id, line)

        process.stdout.close()
        process.wait()

        if process.returncode == 0:
            jobs[job_id]["status"] = "completed"
            append_log(job_id, "\nWorkflow completed successfully.\n")
        else:
            jobs[job_id]["status"] = "failed"
            append_log(job_id, f"\nWorkflow failed with return code {process.returncode}\n")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        append_log(job_id, f"\nERROR: {e}\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/profile", methods=["GET"])
def get_profile():
    return jsonify({"ok": True, "profile": load_saved_profile()})

@app.route("/api/profile", methods=["POST"])
def save_profile():
    profile_json = request.form.get("profile")
    if not profile_json:
        return jsonify({"ok": False, "error": "Missing profile payload."}), 400

    incoming = json.loads(profile_json)
    current = load_saved_profile()

    updated = dict(current)
    for key, value in incoming.items():
        if value is not None:
            updated[key] = value

    resume = request.files.get("resume")
    if resume and resume.filename:
        filename = secure_filename(resume.filename)
        path = UPLOAD_DIR / f"profile_{filename}"
        resume.save(path)
        updated["resume_path"] = str(path.resolve())

    save_profile_json(updated)
    write_env(updated)

    return jsonify({
        "ok": True,
        "message": "Profile saved locally on disk.",
        "profile": updated
    })

@app.route("/api/start", methods=["POST"])
def start():
    recruiters_json = request.form.get("recruiters")
    if not recruiters_json:
        return jsonify({"ok": False, "error": "Missing recruiters payload."}), 400

    recruiters = json.loads(recruiters_json)
    recruiters = [
        r for r in recruiters
        if r.get("firstName", "").strip() and r.get("lastName", "").strip() and r.get("company", "").strip()
    ]
    if not recruiters:
        return jsonify({"ok": False, "error": "Add at least one complete recruiter row."}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "queued", "logs": "", "log_file": ""}

    thread = threading.Thread(target=run_job, args=(job_id, recruiters), daemon=True)
    thread.start()

    return jsonify({"ok": True, "job_id": job_id})

@app.route("/api/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"status": "missing", "logs": "", "log_file": ""}))

if __name__ == "__main__":
    app.run(debug=True, port=5001)
