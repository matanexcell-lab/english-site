from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import json, os
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DATA_FILE = "data.json"

# ---------- קריאה וכתיבה לקובץ ----------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

lists = load_data()

# ---------- דף הבית ----------
@app.route("/")
def home():
    return render_template("index.html")

# ---------- קבלת כל הרשימות ----------
@app.route("/api/lists", methods=["GET"])
def api_get_lists():
    # נחזיר רק רשימות (לא מטה)
    return jsonify({k: v for k, v in lists.items() if not k.startswith("_")})

# ---------- שמירת רשימה ----------
@app.route("/api/lists", methods=["POST"])
def api_save_list():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    words = data.get("words") or []
    if not name:
        return jsonify({"ok": False, "message": "שם רשימה חסר"}), 400

    # מניעת כפילויות + ניקוי
    unique = {}
    for w in words:
        en = (w.get("en") or "").strip()
        he = (w.get("he") or "").strip()
        if not en or not he:
            continue
        key = en.lower()
        if key not in unique:
            unique[key] = {
                "en": en,
                "he": he,
                "correct": int(w.get("correct", 0)),
                "wrong": int(w.get("wrong", 0))
            }
    lists[name] = list(unique.values())
    save_data(lists)
    return jsonify({"ok": True})

# ---------- עדכון תאריך חידון ----------
@app.route("/api/update_quiz_date", methods=["POST"])
def api_update_quiz_date():
    data = request.get_json(force=True, silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name or list_name not in lists:
        return jsonify({"ok": False, "message": "רשימה לא נמצאה"}), 404

    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    data_all = load_data()
    dates = data_all.get("_last_quiz_dates")
    if not isinstance(dates, dict):  # ← זה התיקון לשגיאה שלך
        dates = {}

    dates[list_name] = now
    data_all["_last_quiz_dates"] = dates

    # עדכון רשימות
    data_all.update(lists)
    save_data(data_all)

    return jsonify({"ok": True, "last_quiz": now})

@app.route("/api/last_quiz_dates", methods=["GET"])
def api_last_quiz_dates():
    data = load_data()
    dates = data.get("_last_quiz_dates", {})
    if not isinstance(dates, dict):
        dates = {}
    return jsonify(dates)

# ---------- ייבוא / ייצוא אקסל ----------
REQUIRED_COLS = [
    "words in English",
    "תרגום בעברית",
    "כמה פעמים ענית נכון",
    "כמה פעמים ענית לא נכון",
    "שם הרשימה"
]

@app.route("/api/import_excel", methods=["POST"])
def api_import_excel():
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "לא נשלח קובץ"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "message": "שם הקובץ ריק"}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"ok": False, "message": f"שגיאה בקריאת הקובץ: {e}"}), 400

    for col in REQUIRED_COLS:
        if col not in df.columns:
            return jsonify({"ok": False, "message": f"חסרה עמודה בשם {col}"}), 400

    added = 0
    for _, row in df.iterrows():
        list_name = str(row["שם הרשימה"]).strip()
        if not list_name:
            continue

        en = str(row["words in English"]).strip()
        he = str(row["תרגום בעברית"]).strip()
        if not en or not he:
            continue

        correct = int(row["כמה פעמים ענית נכון"]) if pd.notna(row["כמה פעמים ענית נכון"]) else 0
        wrong = int(row["כמה פעמים ענית לא נכון"]) if pd.notna(row["כמה פעמים ענית לא נכון"]) else 0

        if list_name not in lists:
            lists[list_name] = []

        # מניעת כפילויות
        if any(w["en"].lower() == en.lower() for w in lists[list_name]):
            continue

        if len(lists[list_name]) >= 15:
            continue

        lists[list_name].append({"en": en, "he": he, "correct": correct, "wrong": wrong})
        added += 1

    save_data(lists)
    return jsonify({"ok": True, "message": f"ייבוא הושלם ({added} מילים נוספו)."})


@app.route("/api/download_excel", methods=["GET"])
def api_download_excel():
    rows = []
    dates = load_data().get("_last_quiz_dates", {})
    for list_name, words in lists.items():
        if list_name.startswith("_"):  # דלג על מטה
            continue
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": int(w.get("correct", 0)),
                "כמה פעמים ענית לא נכון": int(w.get("wrong", 0)),
                "שם הרשימה": list_name
            })
    if not rows:
        return jsonify({"ok": False, "message": "אין נתונים לייצוא."}), 200

    df = pd.DataFrame(rows)
    path = "all_words_export.xlsx"
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

# ---------- הרצה מקומית ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)