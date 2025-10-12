from flask import Flask, render_template, jsonify, request
import json, os
from math import inf

app = Flask(__name__)
DATA_FILE = "data.json"

# --- קריאה וכתיבה לקובץ הנתונים ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- חישוב יחס ---
def compute_ratio(ok, bad):
    if ok == 0:
        if bad > 0:
            return inf
        return 0.0
    return bad / ok

# --- דף הבית ---
@app.route("/")
def home():
    return render_template("index.html")

# --- רשימת כל הרשימות ---
@app.route("/api/lists", methods=["GET"])
def get_lists():
    data = load_data()
    lists = []
    for name, words in data.items():
        ok_total = sum(w.get("ok", 0) for w in words)
        bad_total = sum(w.get("bad", 0) for w in words)
        lists.append({
            "name": name,
            "count": len(words),
            "ok": ok_total,
            "bad": bad_total
        })
    return jsonify({"lists": lists})

# --- יצירת רשימה חדשה ---
@app.route("/api/lists", methods=["POST"])
def create_list():
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "שם הרשימה ריק"})
    data = load_data()
    if name in data:
        return jsonify({"ok": False, "error": "הרשימה כבר קיימת"})
    data[name] = []
    save_data(data)
    return jsonify({"ok": True})

# --- שליפת רשימה אחת ---
@app.route("/api/list/<name>")
def get_list(name):
    data = load_data()
    lst = data.get(name, [])
    words = []
    for w in lst:
        ok = int(w.get("ok", 0))
        bad = int(w.get("bad", 0))
        ratio = compute_ratio(ok, bad)
        words.append({
            "en": w["en"],
            "he": w["he"],
            "ok": ok,
            "bad": bad,
            "ratio": ratio
        })
    # מיין לפי יחס יורד (∞ ראשון)
    words.sort(key=lambda x: (x["ratio"] if x["ratio"] != inf else 1e18), reverse=True)
    return jsonify({"ok": True, "words": words})

# --- הוספת מילה ---
@app.route("/api/words", methods=["POST"])
def add_word():
    req = request.json
    list_name = req.get("list")
    en = req.get("en", "").strip()
    he = req.get("he", "").strip()
    if not list_name or not en or not he:
        return jsonify({"ok": False, "error": "נתונים חסרים"})

    data = load_data()
    if list_name not in data:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"})
    lst = data[list_name]
    if len(lst) >= 15:
        return jsonify({"ok": False, "error": "לא ניתן להוסיף יותר מ-15 מילים"})

    for w in lst:
        if w["en"].lower() == en.lower():
            return jsonify({"ok": False, "error": "המילה כבר קיימת"})

    lst.append({"en": en, "he": he, "ok": 0, "bad": 0})
    save_data(data)
    return jsonify({"ok": True})

# --- מחיקת מילה ---
@app.route("/api/words", methods=["DELETE"])
def delete_word():
    list_name = request.args.get("list")
    en = request.args.get("en")
    he = request.args.get("he")

    data = load_data()
    if list_name not in data:
        return jsonify({"ok": False, "error": "הרשימה לא נמצאה"})

    data[list_name] = [w for w in data[list_name] if not (w["en"] == en and w["he"] == he)]
    save_data(data)
    return jsonify({"ok": True})

# --- עדכון תשובה בחידון ---
@app.route("/api/answer", methods=["POST"])
def update_answer():
    req = request.json
    list_name = req.get("list")
    en = req.get("en")
    he = req.get("he")
    correct = req.get("correct")

    data = load_data()
    if list_name not in data:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"})
    for w in data[list_name]:
        if w["en"] == en and w["he"] == he:
            if correct:
                w["ok"] = w.get("ok", 0) + 1
            else:
                w["bad"] = w.get("bad", 0) + 1
            break
    save_data(data)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
