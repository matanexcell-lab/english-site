from flask import Flask, request, jsonify, render_template
import json
import pandas as pd
import os

app = Flask(__name__, static_folder="static", template_folder="templates")

DATA_FILE = "data.json"

# --- טעינת נתונים ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

# --- שמירת נתונים ---
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/")
def index():
    return render_template("index.html")

# --- החזרת רשימות ---
@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(load_data())

# --- עדכון / יצירת רשימה ---
@app.route("/api/lists", methods=["POST"])
def save_list():
    data = load_data()
    req = request.get_json()
    name = req["name"]
    words = req["words"]
    data[name] = words
    save_data(data)
    return jsonify({"ok": True})

# --- ייבוא קובץ אקסל ---
@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    try:
        file = request.files["file"]
        df = pd.read_excel(file)

        # שמות עמודות נדרשים
        required_cols = [
            "words in English",
            "תרגום בעברית",
            "כמה פעמים ענית נכון",
            "כמה פעמים ענית לא נכון",
            "שם הרשימה"
        ]

        # בדיקה שהעמודות קיימות
        for col in required_cols:
            if col not in df.columns:
                return jsonify({"ok": False, "message": f"חסרה עמודה בשם {col}"}), 400

        data = load_data()
        for _, row in df.iterrows():
            en = str(row["words in English"]).strip()
            he = str(row["תרגום בעברית"]).strip()
            correct = int(row["כמה פעמים ענית נכון"]) if not pd.isna(row["כמה פעמים ענית נכון"]) else 0
            wrong = int(row["כמה פעמים ענית לא נכון"]) if not pd.isna(row["כמה פעמים ענית לא נכון"]) else 0
            list_name = str(row["שם הרשימה"]).strip() or "רשימה 1"

            if list_name not in data:
                data[list_name] = []

            data[list_name].append({
                "en": en,
                "he": he,
                "correct": correct,
                "wrong": wrong
            })

        save_data(data)
        return jsonify({"ok": True, "message": "📥 ייבוא הושלם בהצלחה!"})

    except Exception as e:
        return jsonify({"ok": False, "message": f"שגיאה בעת ייבוא הקובץ: {e}"}), 500

# --- ייצוא לאקסל ---
@app.route("/api/export_excel", methods=["GET"])
def export_excel():
    data = load_data()
    rows = []
    for list_name, words in data.items():
        for w in words:
            rows.append({
                "words in English": w["en"],
                "תרגום בעברית": w["he"],
                "כמה פעמים ענית נכון": w.get("correct", 0),
                "כמה פעמים ענית לא נכון": w.get("wrong", 0),
                "שם הרשימה": list_name
            })

    df = pd.DataFrame(rows)
    out_path = "exported_words.xlsx"
    df.to_excel(out_path, index=False)
    return jsonify({"ok": True, "message": "📤 קובץ ייצוא נוצר בהצלחה!", "file": out_path})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
