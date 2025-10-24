from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import pandas as pd
import os, json, base64, requests, atexit

app = Flask(__name__, static_folder=".", static_url_path="")
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

# === עמוד הבית (index.html) ===
@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# === קבלת כל הרשימות ===
@app.route("/api/lists", methods=["GET"])
def get_lists():
    return jsonify(lists)


# === שמירת רשימה ===
@app.route("/api/lists", methods=["POST"])
def save_list():
    data = request.get_json()
    name = data["name"]
    words = data["words"]
    lists[name] = words
    save_data()
    return jsonify({"ok": True})


# === ייבוא קובץ Excel ===
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


# === הורדת כל הנתונים לקובץ Excel ===
@app.route("/api/download_excel", methods=["GET"])
def download_excel():
    rows = []
    for list_name, words in lists.items():
        if not isinstance(words, list):
            continue
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


# === עדכון תאריך אחרון של חידון ===
@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    data = request.get_json()
    name = data.get("list_name")
    if name in lists:
        lists[name + "_last_quiz"] = pd.Timestamp.now().isoformat()
        save_data()
        return jsonify({"ok": True})
    return jsonify({"ok": False})


# === גיבוי ל-GitHub בזמן כיבוי ===
def backup_to_github():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        print("⚠️ אין פרטי גישה לגיבוי GitHub — מדלג.")
        return

    print("📤 מבצע גיבוי ל-GitHub...")
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        encoded = base64.b64encode(content.encode()).decode()

        url = f"https://api.github.com/repos/{repo}/contents/data.json"
        headers = {"Authorization": f"token {token}"}
        payload = {
            "message": "Auto backup from Render",
            "content": encoded
        }
        res = requests.put(url, headers=headers, json=payload)
        print(f"✅ גיבוי ל-GitHub הושלם: {res.status_code}")
    except Exception as e:
        print(f"❌ שגיאה בגיבוי: {e}")

atexit.register(backup_to_github)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)