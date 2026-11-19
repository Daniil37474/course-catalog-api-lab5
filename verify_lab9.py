"""Live HTTP evidence for Lab 9; run once after bootstrap.py --reset-demo."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
import statistics
import subprocess
from time import perf_counter

import httpx
import jwt
from config import settings
from security import ALGORITHM, ISSUER

API = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "verification"
OUT.mkdir(exist_ok=True)

def run():
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "rest": [], "tokens": {}}
    with httpx.Client(base_url=API, timeout=20) as client:
        tokens = {}
        for role, email, password in [
            ("student", "aigerim@example.com", "aigerim-demo-pass"),
            ("admin", "admin@example.com", "admin-demo-password"),
        ]:
            r = client.post("/auth/login", data={"username": email, "password": password})
            r.raise_for_status()
            tokens[role] = r.json()["access_token"]
        def auth(role):
            return {} if role == "anonymous" else {"Authorization": "Bearer " + tokens[role]}
        for method, path, body in [
            ("GET", "/courses", None), ("GET", "/me", None), ("GET", "/enrollments", None),
            ("POST", "/enrollments", {"courseId": "api-design", "studentId": 1}),
            ("POST", "/enrollments", {"courseId": "web-security", "studentId": 2}),
        ]:
            row = {"request": method + " " + path, "studentId": body["studentId"] if body else None}
            for role in ["anonymous", "student", "admin"]:
                if method == "POST" and body["studentId"] == 1 and role == "admin":
                    row[role] = "N/A: administrator has no own student profile"
                    continue
                r = client.request(method, path, json=body, headers=auth(role))
                row[role] = r.status_code
            report["rest"].append(row)

        unknown, known = [], []
        bodies = []
        for _ in range(12):
            for email, series in [("nobody@example.com", unknown), ("aigerim@example.com", known)]:
                start = perf_counter()
                r = client.post("/auth/login", data={"username": email, "password": "wrong-password-123"})
                series.append((perf_counter() - start) * 1000)
                bodies.append(r.json())
                assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
        report["login"] = {
            "same_error_body": all(body == bodies[0] for body in bodies),
            "samples_per_case": 12,
            "unknown_email_median_ms": round(statistics.median(unknown), 2),
            "known_email_wrong_password_median_ms": round(statistics.median(known), 2),
            "rate_limiting": "not implemented; propose a shared limiter per account and IP, 429 with Retry-After",
        }
        now = datetime.now(timezone.utc)
        sub = jwt.decode(tokens["student"], settings.secret_key, algorithms=[ALGORITHM], issuer=ISSUER)["sub"]
        base = {"sub": sub, "iss": ISSUER, "iat": now, "exp": now + timedelta(minutes=15)}
        cases = {
            "expired": jwt.encode(dict(base, exp=now-timedelta(seconds=1)), settings.secret_key, algorithm=ALGORITHM),
            "foreign-key": jwt.encode(base, "foreign-" * 8, algorithm=ALGORITHM),
            "no-exp": jwt.encode({k:v for k,v in base.items() if k != "exp"}, settings.secret_key, algorithm=ALGORITHM),
            "wrong-issuer": jwt.encode(dict(base, iss="foreign-api"), settings.secret_key, algorithm=ALGORITHM),
            "alg-none": jwt.encode(base, "", algorithm="none"),
            "invalid-sub": jwt.encode(dict(base, sub="abc"), settings.secret_key, algorithm=ALGORITHM),
            "forged": "forged.token.value",
        }
        for label, token in cases.items():
            r = client.get("/me", headers={"Authorization": "Bearer " + token})
            report["tokens"][label] = r.status_code
            assert r.status_code == 401

        report["graphql"] = []
        for label, query, role in [
            ("anonymous me", "{ me { email } }", "anonymous"),
            ("student me", "{ me { email role } }", "student"),
            ("student lists students", "{ students { name email } }", "student"),
            ("admin lists students", "{ students { name email } }", "admin"),
            ("other student's email", '{ student(id: "2") { name email } }', "student"),
            ("nested email", "{ enrollments { student { id name email } } }", "student"),
        ]:
            r = client.post("/graphql", json={"query": query}, headers=auth(role))
            report["graphql"].append({"case": label, "http": r.status_code, "response": r.json()})

        curl = shutil.which("curl")
        if curl:
            # Capture credentials/tokens internally and never put them in the evidence output.
            login = subprocess.run([curl, "-sS", "-X", "POST", API + "/auth/login",
                                    "-d", "username=aigerim@example.com", "-d", "password=aigerim-demo-pass"],
                                   check=True, capture_output=True, text=True)
            bearer = json.loads(login.stdout)["access_token"]
            me = subprocess.run([curl, "-sS", "-w", "\n%{http_code}", API + "/me",
                                 "-H", "Authorization: Bearer " + bearer],
                                check=True, capture_output=True, text=True)
            body, status = me.stdout.rsplit("\n", 1)
            report["curl"] = {"login": 200, "me": int(status), "profile": json.loads(body)}
    (OUT / "api-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rest": report["rest"], "login": report["login"], "tokens": report["tokens"],
                      "curl": report.get("curl")}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
