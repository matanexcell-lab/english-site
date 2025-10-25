from flask import Flask, request, jsonify, send_file
import pandas as pd
import json, os, datetime, io

app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_FILE = "words_data.json"
DATE_FILE = "quiz_dates.json"

# ---------- קריאה וכתיבה של הנתונים ----------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_dates():
    if not os.path.exists(DATE_FILE):
        return {}
    with open(DATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_dates(data):
    with open(DATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- ראוטים ----------
@app.route("/")
def home():
    return send_file("templates/index.html")

@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(load_data())

@app.route("/api/lists", methods=["POST"])
def save_list():
    body = request.json
    if not body or "name" not in body:
        return jsonify({"error": "missing name"}), 400
    data = load_data()
    data[body["name"]] = body.get("words", [])
    save_data(data)
    return jsonify({"ok": True})

@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    data = request.get_json()
    list_name = data.get("list_name")
    date = data.get("date") or datetime.datetime.now().isoformat()
    dates = load_dates()
    dates[list_name] = date
    save_dates(dates)
    return jsonify({"ok": True})

@app.route("/api/last_quiz_dates", methods=["GET"])
def last_quiz_dates():
    return jsonify(load_dates())

# ---------- העברת מילה מרשימה לרשימה ----------
@app.route("/api/move_word", methods=["POST"])
def move_word():
    data = request.json
    from_list = data.get("from_list")
    to_list = data.get("to_list")
    word = data.get("word")

    all_data = load_data()
    if from_list not in all_data or to_list not in all_data:
        return jsonify({"ok": False, "message": "רשימה לא קיימת"})

    word_obj = next((w for w in all_data[from_list] if w["en"] == word), None)
    if not word_obj:
        return jsonify({"ok": False, "message": "המילה לא נמצאה"})

    all_data[from_list] = [w for w in all_data[from_list] if w["en"] != word]
    all_data[to_list].append(word_obj)
    save_data(all_data)
    return jsonify({"ok": True, "message": f"המילה '{word}' הועברה מ'{from_list}' אל '{to_list}' בהצלחה ✅"})

# ---------- ייבוא מאקסל (כולל תאריך אחרון חידון) ----------
@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "לא נבחר קובץ"})
    file = request.files["file"]

    try:
        df = pd.read_excel(file)
        required_cols = ["words in English", "תרגום בעברית", "כמה פעמים ענית נכון", "כמה פעמים ענית לא נכון", "שם הרשימה"]
        for col in required_cols:
            if col not in df.columns:
                return jsonify({"ok": False, "message": f"עמודה חסרה: {col}"})

        data = load_data()
        dates = load_dates()

        for _, row in df.iterrows():
            list_name = str(row["שם הרשימה"]).strip()
            if not list_name:
                continue
            if list_name not in data:
                data[list_name] = []

            en = str(row["words in English"]).strip()
            he = str(row["תרגום בעברית"]).strip()
            correct = int(row["כמה פעמים ענית נכון"])
            wrong = int(row["כמה פעמים ענית לא נכון"])

            exists = any(w["en"].lower() == en.lower() for w in data[list_name])
            if not exists:
                data[list_name].append({
                    "en": en,
                    "he": he,
                    "correct": correct,
                    "wrong": wrong
                })

            # אם קיימת עמודת תאריך — נעדכן את רשימת התאריכים
            if "תאריך אחרון חידון" in df.columns:
                last_date = str(row["תאריך אחרון חידון"]).strip()
                if last_date and last_date.lower() != "nan":
                    dates[list_name] = last_date

        save_data(data)
        save_dates(dates)
        return jsonify({"ok": True, "message": f"הקובץ נטען בהצלחה ({len(df)} שורות)"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

# ---------- ייצוא לאקסל (כולל תאריך אחרון חידון) ----------
@app.route("/api/download_excel")
def download_excel():
    data = load_data()
    dates = load_dates()
    rows = []

    for list_name, words in data.items():
        last_quiz = dates.get(list_name, "")
        for w in words:
            rows.append({
                "words in English": w.get("en", ""),
                "תרגום בעברית": w.get("he", ""),
                "כמה פעמים ענית נכון": w.get("correct", 0),
                "כמה פעמים ענית לא נכון": w.get("wrong", 0),
                "שם הרשימה": list_name,
                "תאריך אחרון חידון": last_quiz
            })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="all_words_export.xlsx")

# ---------- הרצה ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)