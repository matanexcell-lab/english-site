from flask import Flask, render_template, jsonify, request
import json, os
import pandas as pd

app = Flask(__name__)
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/")
def home():
    return render_template("index.html")

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
    return jsonify({"ok": True})

# --- ייבוא קובץ Excel ---
@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    if "file" not in request.files:
        return jsonify({"message": "❌ לא נבחר קובץ", "ok": False})

    file = request.files["file"]
    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"message": f"שגיאה בקריאת הקובץ: {e}", "ok": False})

    required_cols = ["words in English", "תרגום בעברית", "כמה פעמים ענית נכון", "כמה פעמים ענית לא נכון", "שם הרשימה"]
    for col in required_cols:
        if col not in df.columns:
            return jsonify({"message": f"חסרה עמודה בשם {col}", "ok": False})

    data = load_data()
    added = 0
    skipped = 0

    for _, row in df.iterrows():
        name = str(row["שם הרשימה"]).strip()
        if not name:
            continue

        en = str(row["words in English"]).strip()
        he = str(row["תרגום בעברית"]).strip()
        correct = int(row["כמה פעמים ענית נכון"]) if not pd.isna(row["כמה פעמים ענית נכון"]) else 0
        wrong = int(row["כמה פעמים ענית לא נכון"]) if not pd.isna(row["כמה פעמים ענית לא נכון"]) else 0

        if name not in data:
            data[name] = []

        # --- בדוק אם המילה כבר קיימת ---
        exists = any(w["en"] == en and w["he"] == he for w in data[name])
        if exists:
            skipped += 1
            continue

        data[name].append({"en": en, "he": he, "correct": correct, "wrong": wrong})
        added += 1

    save_data(data)
    return jsonify({
        "message": f"✅ הייבוא הושלם! נוספו {added} מילים חדשות. דולגו {skipped} שכבר קיימות.",
        "ok": True
    })

# --- ייצוא לקובץ Excel ---
@app.route("/api/export_excel")
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
    path = "exported_words.xlsx"
    df.to_excel(path, index=False)
    return jsonify({"message": "📦 קובץ Excel נוצר בהצלחה בתיקייה!", "ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)