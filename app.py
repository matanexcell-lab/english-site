from flask import Flask, render_template, jsonify, request, send_file
import json, os
import pandas as pd
from io import BytesIO

app = Flask(__name__)
DATA_FILE = "data.json"


# ===== קריאה וכתיבה =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===== דף הבית =====
@app.route("/")
def home():
    return render_template("index.html")


# ===== רשימות =====
@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(load_data())

@app.route("/api/lists", methods=["POST"])
def save_list():
    data = load_data()
    new_list = request.json
    name = new_list["name"]
    data[name] = new_list["words"]
    save_data(data)
    return jsonify({"message": "נשמר בהצלחה!"})


# ===== ייבוא מקובץ Excel =====
@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "לא נשלח קובץ"})
    file = request.files["file"]
    try:
        df = pd.read_excel(BytesIO(file.read()))
    except Exception as e:
        return jsonify({"ok": False, "error": f"שגיאה בקריאת הקובץ: {e}"})

    expected = [
        "words in English",
        "תרגום בעברית",
        "כמה פעמים ענית נכון",
        "כמה פעמים ענית לא נכון",
        "שם הרשימה"
    ]
    for col in expected:
        if col not in df.columns:
            return jsonify({"ok": False, "error": f"חסרה עמודה בשם {col}"})

    data = load_data()
    for _, row in df.iterrows():
        en = str(row["words in English"]).strip()
        he = str(row["תרגום בעברית"]).strip()
        ok = int(row["כמה פעמים ענית נכון"]) if not pd.isna(row["כמה פעמים ענית נכון"]) else 0
        bad = int(row["כמה פעמים ענית לא נכון"]) if not pd.isna(row["כמה פעמים ענית לא נכון"]) else 0
        list_name = str(row["שם הרשימה"]).strip()

        if not en or not he or not list_name:
            continue

        if list_name not in data:
            data[list_name] = []

        exists = any(w["en"].lower() == en.lower() for w in data[list_name])
        if not exists:
            data[list_name].append({"en": en, "he": he, "ok": ok, "bad": bad})

    save_data(data)
    return jsonify({"ok": True, "message": "ייבוא הסתיים בהצלחה!"})


# ===== ייצוא לאקסל =====
@app.route("/api/export_excel")
def export_excel():
    data = load_data()
    rows = []
    for list_name, words in data.items():
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": w.get("ok", 0),
                "כמה פעמים ענית לא נכון": w.get("bad", 0),
                "שם הרשימה": list_name
            })

    if not rows:
        return jsonify({"ok": False, "error": "אין נתונים לייצוא"})

    output = BytesIO()
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="words")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="english_words_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
