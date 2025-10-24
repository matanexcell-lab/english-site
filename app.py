from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import pandas as pd
import os
import json
import requests
import base64
import atexit

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DATA_FILE = "data.json"

# --- טעינת נתונים קיימים ---
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lists = json.load(f)
else:
    lists = {}

def save_data():
    """שומר את הנתונים לקובץ JSON"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(lists, f, ensure_ascii=False, indent=2)

@app.route("/")
def home():
    return send_file("templates/index.html")

@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(lists)

@app.route("/api/lists", methods=["POST"])
def save_list():
    data = request.get_json()
    name = data["name"]
    words = data["words"]
    lists[name] = words
    save_data()
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

        # בדיקה אם המילה כבר קיימת
        exists = any(w["en"].lower() == en.lower() for w in lists[list_name])
        if not exists:
            lists[list_name].append({
                "en": en,
                "he": he,
                "correct": correct,
                "wrong": wrong
            })
            added_count += 1

    save_data()
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
    list_name = data.get("list_name")
    if list_name in lists:
        if not isinstance(lists[list_name], list):
            lists[list_name] = []
        lists[list_name].append({"_last_quiz": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")})
        save_data()
    return jsonify({"ok": True})

# --- גיבוי ל-GitHub ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

def backup_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        b64 = base64.b64encode(content.encode()).decode()
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DATA_FILE}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha", "")
        data = {
            "message": "Auto backup",
            "content": b64,
            "sha": sha
        }
        requests.put(url, headers=headers, json=data)
        print("✅ גיבוי נשמר ב-GitHub בהצלחה")
    except Exception as e:
        print("⚠️ שגיאת גיבוי ל-GitHub:", e)

atexit.register(backup_to_github)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)