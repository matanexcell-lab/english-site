from flask import Flask, render_template, jsonify, request
import json, os

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

# --- רשימות ---
@app.route("/api/lists", methods=["GET"])
def get_lists():
    data = load_data()
    lists = []
    for name, words in data.items():
        ok = sum(w.get("ok", 0) for w in words)
        bad = sum(w.get("bad", 0) for w in words)
        lists.append({"name": name, "count": len(words), "ok": ok, "bad": bad})
    return jsonify({"ok": True, "lists": lists})

@app.route("/api/lists", methods=["POST"])
def create_list():
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "שם רשימה חסר"})
    data = load_data()
    if name in data:
        return jsonify({"ok": False, "error": "הרשימה כבר קיימת"})
    data[name] = []
    save_data(data)
    return jsonify({"ok": True})

# --- מילים ---
@app.route("/api/list/<name>", methods=["GET"])
def get_list(name):
    data = load_data()
    words = data.get(name, [])
    # חישוב יחס לכל מילה
    for w in words:
        ok = w.get("ok", 0)
        bad = w.get("bad", 0)
        w["ratio"] = round(bad / (ok + 1), 2)
    # מיון לפי יחס יורד
    words.sort(key=lambda w: w["ratio"], reverse=True)
    return jsonify({"ok": True, "words": words})

@app.route("/api/words", methods=["POST"])
def add_word():
    data = load_data()
    list_name = request.json.get("list")
    en = request.json.get("en", "").strip()
    he = request.json.get("he", "").strip()
    if not list_name or not en or not he:
        return jsonify({"ok": False, "error": "נתונים חסרים"})
    if list_name not in data:
        return jsonify({"ok": False, "error": "רשימה לא קיימת"})
    if len(data[list_name]) >= 15:
        return jsonify({"ok": False, "error": "אי אפשר להוסיף יותר מ-15 מילים"})
    # אם המילה כבר קיימת - לא להוסיף שוב
    for w in data[list_name]:
        if w["en"] == en and w["he"] == he:
            return jsonify({"ok": False, "error": "המילה כבר קיימת"})
    data[list_name].append({"en": en, "he": he, "ok": 0, "bad": 0})
    save_data(data)
    return jsonify({"ok": True})

@app.route("/api/words", methods=["DELETE"])
def delete_word():
    list_name = request.args.get("list")
    en = request.args.get("en")
    he = request.args.get("he")
    data = load_data()
    if list_name in data:
        data[list_name] = [w for w in data[list_name] if not (w["en"] == en and w["he"] == he)]
        save_data(data)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "הרשימה לא נמצאה"})

# --- עדכון תוצאה ---
@app.route("/api/answer", methods=["POST"])
def record_answer():
    body = request.json
    list_name = body.get("list")
    en = body.get("en")
    he = body.get("he")
    correct = body.get("correct")
    data = load_data()
    if list_name in data:
        for w in data[list_name]:
            if w["en"] == en and w["he"] == he:
                if correct:
                    w["ok"] = w.get("ok", 0) + 1
                else:
                    w["bad"] = w.get("bad", 0) + 1
        save_data(data)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
