from flask import Flask, request, jsonify, send_file
import pandas as pd
import json, os, datetime, io

app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_FILE = "words_data.json"
DATE_FILE = "quiz_dates.json"

# === עוזרים לשמירה וטעינה של נתונים ===
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


@app.route("/")
def home():
    return send_file("templates/index.html")


# === קבלת רשימות ===
@app.route("/api/lists", methods=["GET"])
def get_lists():
    data = load_data()
    return jsonify(data)


# === שמירת רשימה ===
@app.route("/api/lists", methods=["POST"])
def save_list():
    body = request.json
    if not body or "name" not in body:
        return jsonify({"error": "missing name"}), 400

    data = load_data()
    data[body["name"]] = body.get("words", [])
    save_data(data)
    return jsonify({"ok": True})


# === שמירת תאריך חידון ===
@app.route("/api/update_quiz_date", methods=["POST"])
def api_update_quiz_date():
    try:
        data = request.get_json()
        list_name = data.get("list_name")
        date = data.get("date")

        if not list_name:
            return jsonify({"ok": False, "error": "no list_name"}), 400

        dates = load_dates()
        # אם לא נשלח תאריך — נשתמש בזמן נוכחי
        dates[list_name] = date or datetime.datetime.now().isoformat()
        save_dates(dates)

        print(f"✅ עודכן תאריך חידון עבור: {list_name}")
        return jsonify({"ok": True})
    except Exception as e:
        print("❌ שגיאה בעדכון תאריך:", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# === קבלת תאריכי חידון ===
@app.route("/api/last_quiz_dates", methods=["GET"])
def api_last_quiz_dates():
    dates = load_dates()
    return jsonify(dates)


# === ייבוא קובץ Excel ===
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

            # מניעת כפילות
            exists = any(w["en"].lower() == en.lower() for w in data[list_name])
            if not exists:
                data[list_name].append({
                    "en": en,
                    "he": he,
                    "correct": correct,
                    "wrong": wrong
                })

        save_data(data)
        return jsonify({"ok": True, "message": f"הקובץ נטען בהצלחה ({len(df)} שורות)"})

    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


# === הורדת הנתונים כקובץ Excel ===
@app.route("/api/download_excel")
def download_excel():
    data = load_data()
    rows = []
    for list_name, words in data.items():
        for w in words:
            rows.append({
                "words in English": w.get("en", ""),
                "תרגום בעברית": w.get("he", ""),
                "כמה פעמים ענית נכון": w.get("correct", 0),
                "כמה פעמים ענית לא נכון": w.get("wrong", 0),
                "שם הרשימה": list_name
            })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="all_words_export.xlsx")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)