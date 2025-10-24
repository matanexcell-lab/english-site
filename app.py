from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
import pandas as pd
import os
import json
from datetime import datetime

app = Flask(__name__)
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

# === שליפת כל הרשימות ===
@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(lists)

# === שמירת רשימה אחת ===
@app.route("/api/lists", methods=["POST"])
def save_list():
    data = request.get_json()
    name = data["name"]
    words = data["words"]
    lists[name] = words
    save_data()
    return jsonify({"ok": True})

# === ייבוא מקובץ Excel ===
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

# === ייצוא כל הנתונים לקובץ Excel ===
@app.route("/api/download_excel", methods=["GET"])
def download_excel():
    rows = []
    for list_name, words in lists.items():
        last_quiz = words._last_quiz if isinstance(words, dict) and "_last_quiz" in words else "-"
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": w.get("correct", 0),
                "כמה פעמים ענית לא נכון": w.get("wrong", 0),
                "שם הרשימה": list_name,
                "תאריך חידון אחרון": last_quiz
            })
    if not rows:
        return jsonify({"message": "אין נתונים לייצוא.", "ok": False})
    
    df = pd.DataFrame(rows)
    file_path = "all_words.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)

# === עדכון תאריך חידון אחרון ===
@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    data = request.get_json()
    list_name = data.get("list_name")
    if list_name and list_name in lists:
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        lists[list_name]._last_quiz = now_str
        save_data()
        return jsonify({"ok": True, "date": now_str})
    return jsonify({"ok": False, "error": "רשימה לא נמצאה"})

# === דף הבית ===
@app.route("/")
def index():
    return render_template("index.html")

# === הפעלת השרת ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)