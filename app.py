from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import pandas as pd
import json, os
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DATA_FILE = "data.json"

# ---------- עזרה: קריאה/כתיבה ל־JSON ----------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # נוודא שמבנה הנתונים הוא { list_name: [ {en, he, correct, wrong}, ... ], ... }
                # ושדה מטה לא יפריע בחישובים
                for name, words in list(data.items()):
                    if isinstance(words, dict):
                        # אם בטעות נשמר כ־dict, נהפוך לרשימה ריקה
                        data[name] = words.get("words", [])
                return data
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

# ---------- API: קריאה/שמירה של רשימות ----------
@app.route("/api/lists", methods=["GET"])
def api_get_lists():
    return jsonify(lists)

@app.route("/api/lists", methods=["POST"])
def api_save_list():
    """
    מצפה ל־JSON: { "name": "<list name>", "words": [ {en, he, correct, wrong}, ... ] }
    שומר את הרשימה ומעדכן את הקובץ.
    """
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    words = data.get("words") or []

    if not name:
        return jsonify({"ok": False, "message": "שם רשימה חסר"}), 400

    # מניעת יותר מ־15 מילים
    if len(words) > 15:
        words = words[:15]

    # איחוד כפילויות לפי en (רישיות לא חשובה)
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
                "correct": int(w.get("correct", 0) or 0),
                "wrong": int(w.get("wrong", 0) or 0),
            }
    lists[name] = list(unique.values())
    save_data(lists)
    return jsonify({"ok": True})

# ---------- API: עדכון תאריך חידון ----------
@app.route("/api/update_quiz_date", methods=["POST"])
def api_update_quiz_date():
    data = request.get_json(force=True, silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name or list_name not in lists:
        return jsonify({"ok": False, "message": "רשימה לא נמצאה"}), 404
    # נשמור בתור "שדה מטה" מחוץ לרשימת המילים
    # נשתמש במבנה מיוחד: רשימת מילים + מפתח מיוחד במפה צדדית
    # כדי לשמור על תאימות נשמור ליד הרשימה קובץ צל:
    meta_key = f"__meta__{list_name}"
    lists_meta = load_data().get(meta_key)
    # נקבע עכשיו
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    # נעדכן "שדה מטה" בכללי — פשוט נשמור ב־lists כ־"שדה" של הרשימה
    # כדי לא לשבור את ה־index, נוסיף "תאריך" כמסד נתונים נפרד:
    # טריק: נשים תאריך כאיבר ראשון מסוג dict עם דגל מיוחד, אך עדיף לשמור בקובץ נפרד — נעשה פשוט:
    # נפשט: נוסיף שדה מיוחד ב־lists בתור מפתח עם underline:
    # כדי לא לפגוע בלוגיקה, נשמור "תאריכים" במילון נפרד בתוך הקובץ:
    dates = load_data().get("_last_quiz_dates", {})
    dates[list_name] = now

    # נמזג הכל לקובץ כדי לא לאבד רשימות שהיו בזיכרון
    data_all = load_data()
    data_all.update(lists)
    data_all["_last_quiz_dates"] = dates
    save_data(data_all)
    return jsonify({"ok": True, "last_quiz": now})

@app.route("/api/last_quiz_dates", methods=["GET"])
def api_last_quiz_dates():
    return jsonify(load_data().get("_last_quiz_dates", {}))

# ---------- API: ייבוא/ייצוא אקסל ----------
REQUIRED_COLS = [
    "words in English",
    "תרגום בעברית",
    "כמה פעמים ענית נכון",
    "כמה פעמים ענית לא נכון",
    "שם הרשימה",
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

    # בדיקת כותרות
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

        # מניעת כפילויות (רישיות לא חשובה)
        if any(w["en"].lower() == en.lower() for w in lists[list_name]):
            continue

        if len(lists[list_name]) >= 15:
            # לא נוסיף מעבר ל־15
            continue

        lists[list_name].append({"en": en, "he": he, "correct": correct, "wrong": wrong})
        added += 1

    save_data(lists)
    return jsonify({"ok": True, "message": f"ייבוא הושלם ({added} מילים נוספו)."})


@app.route("/api/download_excel", methods=["GET"])
def api_download_excel():
    rows = []
    # נטען גם תאריכים (לא נכנסים לאקסל, אבל נשמרים בקובץ)
    dates = load_data().get("_last_quiz_dates", {})
    for list_name, words in lists.items():
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": int(w.get("correct", 0) or 0),
                "כמה פעמים ענית לא נכון": int(w.get("wrong", 0) or 0),
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
    # ב־Render ירוץ דרך gunicorn (ראה Procfile)
    app.run(host="0.0.0.0", port=10000)