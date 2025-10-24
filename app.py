from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import pandas as pd
import os, json, base64, requests, atexit

app = Flask(__name__)
CORS(app)

DATA_FILE = "data.json"
REPO = "matanmoalem/english-site"  # שנה לשם המאגר שלך
FILE_PATH_IN_REPO = "data.json"
GITHUB_API = "https://api.github.com/repos"
TOKEN = os.environ.get("GITHUB_TOKEN")

# --- טעינת נתונים קיימים ---
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lists = json.load(f)
else:
    lists = {}

def save_local():
    """שומר רק מקומית"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(lists, f, ensure_ascii=False, indent=2)

def backup_to_github():
    """גיבוי ל-GitHub (מופעל רק עם סגירת השרת)"""
    if not TOKEN:
        print("⚠️ GITHUB_TOKEN not set — skipping sync")
        return
    try:
        print("📤 מבצע גיבוי ל-GitHub...")
        # השגת SHA נוכחי (אם יש)
        r = requests.get(f"{GITHUB_API}/{REPO}/contents/{FILE_PATH_IN_REPO}",
                         headers={"Authorization": f"token {TOKEN}"})
        sha = r.json().get("sha", None)

        data = {
            "message": "Backup data.json before server sleep",
            "content": base64.b64encode(
                json.dumps(lists, ensure_ascii=False, indent=2).encode("utf-8")
            ).decode("utf-8"),
            "branch": "main"
        }
        if sha:
            data["sha"] = sha

        res = requests.put(f"{GITHUB_API}/{REPO}/contents/{FILE_PATH_IN_REPO}",
                           headers={"Authorization": f"token {TOKEN}"}, json=data)
        print("✅ גיבוי ל-GitHub הושלם:", res.status_code)
    except Exception as e:
        print("❌ שגיאת גיבוי ל-GitHub:", e)

# רושם את פעולת הגיבוי שתקרה כששרת Render נכבה
atexit.register(backup_to_github)

@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(lists)

@app.route("/api/lists", methods=["POST"])
def save_list():
    data = request.get_json()
    name = data["name"]
    words = data["words"]
    lists[name] = words
    save_local()
    return jsonify({"ok": True})

@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    file = request.files["file"]
    df = pd.read_excel(file)

    required = ["words in English", "תרגום בעברית", "כמה פעמים ענית נכון", "כמה פעמים ענית לא נכון", "שם הרשימה"]
    for col in required:
        if col not in df.columns:
            return jsonify({"message": f"חסרה עמודה בשם {col}", "ok": False})

    added_count = 0
    for _, row in df.iterrows():
        list_name = str(row["שם הרשימה"]).strip()
        if list_name not in lists:
            lists[list_name] = []

        en = str(row["words in English"]).strip()
        he = str(row["תרגום בעברית"]).strip()
        correct = int(row["כמה פעמים ענית נכון"]) if not pd.isna(row["כמה פעמים ענית נכון"]) else 0
        wrong = int(row["כמה פעמים ענית לא נכון"]) if not pd.isna(row["כמה פעמים ענית לא נכון"]) else 0

        # בדיקה שאין כפל מילים
        exists = any(w["en"].lower() == en.lower() for w in lists[list_name])
        if not exists:
            lists[list_name].append({
                "en": en,
                "he": he,
                "correct": correct,
                "wrong": wrong
            })
            added_count += 1

    save_local()
    return jsonify({"message": f"ייבוא הושלם ({added_count} מילים נוספו).", "ok": True})

@app.route("/api/download_excel", methods=["GET"])
def download_excel():
    rows = []
    for list_name, words in lists.items():
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": w.get("correct", 0),
                "כמה פעמים ענית לא נכון": w.get("wrong", 0),
                "שם הרשימה": list_name
            })
    if not rows:
        return jsonify({"message": "אין נתונים לייצוא.", "ok": False})

    df = pd.DataFrame(rows)
    file_path = "all_words.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    data = request.get_json()
    list_name = data["list_name"]
    from datetime import datetime
    if list_name in lists:
        lists[list_name].append({"_last_quiz": datetime.now().isoformat()})
        save_local()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)