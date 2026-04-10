from flask import Flask, request, jsonify, render_template
import subprocess, threading, json, uuid, csv
from pathlib import Path
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

jobs = {}

def write_env(profile, resume_path):
    env_path = BASE_DIR / ".env"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"GMAIL_ADDRESS={profile.get('gmail_address','')}\n")
        f.write(f"GMAIL_APP_PASSWORD={profile.get('gmail_app_password','')}\n")
        f.write(f"YOUR_NAME={profile.get('your_name','')}\n")
        f.write(f"YOUR_PHONE={profile.get('your_phone','')}\n")
        f.write(f"YOUR_LINKEDIN={profile.get('your_linkedin','')}\n")
        f.write(f"YOUR_GITHUB={profile.get('your_github','')}\n")
        f.write(f"YOUR_PORTFOLIO={profile.get('your_portfolio','')}\n")
        f.write(f"RESUME_PATH={resume_path}\n")

def create_csv(recruiters, job_id):
    file_path = BASE_DIR / f"people_{job_id}.csv"
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["FirstName", "LastName", "Company"])
        for r in recruiters:
            writer.writerow([r["firstName"], r["lastName"], r["company"]])
    return file_path

def run_job(job_id, recruiters, profile, resume_file):
    jobs[job_id]["status"] = "running"
    try:
        if resume_file and resume_file.filename:
            filename = secure_filename(resume_file.filename)
            path = UPLOAD_DIR / f"{job_id}_{filename}"
            resume_file.save(path)
            resume_path = str(path)
        else:
            resume_path = profile.get("resume_path", "")

        if not resume_path:
            raise ValueError("Resume path or upload is required.")

        write_env(profile, resume_path)
        csv_file = create_csv(recruiters, job_id)

        cmd = [
            "python",
            "email_pnc_generator.py",
            "--input-csv",
            str(csv_file),
            "--auto-run",
            "--resume-path",
            resume_path
        ]

        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        logs = ""
        for line in process.stdout:
            logs += line
            jobs[job_id]["logs"] = logs

        process.wait()
        jobs[job_id]["status"] = "completed" if process.returncode == 0 else "failed"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["logs"] += f"\nERROR: {e}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    recruiters = json.loads(request.form["recruiters"])
    profile = json.loads(request.form["profile"])
    resume = request.files.get("resume")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "queued", "logs": ""}

    thread = threading.Thread(target=run_job, args=(job_id, recruiters, profile, resume), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})

@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {}))

if __name__ == "__main__":
    app.run(debug=True)
