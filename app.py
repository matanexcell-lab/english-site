from flask import Flask, render_template, jsonify, request
import json, os
from werkzeug.utils import secure_filename

app = Flask(__name__)
DATA_FILE = "data.json"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------- Storage helpers --------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lists": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def get_list(d, name):
    return d["lists"].get(name, [])

def word_key(en, he):
    # מזהה מילים פשוט
    return (en or "").strip().lower(), (he or "").strip().lower()

# -------- Pages --------
@app.route("/")
def home():
    return render_template("index.html")

# -------- Lists API --------
@app.route("/api/lists", methods=["GET"])
def api_lists_get():
    d = load_data()
    out = []
    for name, words in d["lists"].items():
        ok = sum(w.get("ok", 0) for w in words)
        bad = sum(w.get("bad", 0) for w in words)
        out.append({
            "name": name,
            "count": len(words),
            "ok": ok,
            "bad": bad,
        })
    return jsonify({"ok": True, "lists": out})

@app.route("/api/lists", methods=["POST"])
def api_lists_create():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "שם רשימה חסר"}), 400
    d = load_data()
    if name in d["lists"]:
        return jsonify({"ok": False, "error": "רשימה כבר קיימת"}), 400
    d["lists"][name] = []
    save_data(d)
    return jsonify({"ok": True})

@app.route("/api/list/<name>", methods=["GET"])
def api_list_get(name):
    d = load_data()
    words = get_list(d, name)
    return jsonify({"ok": True, "words": words, "count": len(words)})

# -------- Words API --------
@app.route("/api/words", methods=["POST"])
def api_word_add():
    """Body: {list, en, he} – עד 15 מילים לרשימה."""
    data = request.json or {}
    lst = (data.get("list") or "").strip()
    en = (data.get("en") or "").strip()
    he = (data.get("he") or "").strip()
    if not lst or not en or not he:
        return jsonify({"ok": False, "error": "חסרים נתונים"}), 400

    d = load_data()
    if lst not in d["lists"]:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"}), 404

    words = d["lists"][lst]
    if len(words) >= 15:
        return jsonify({"ok": False, "error": "מקסימום 15 מילים לרשימה"}), 400

    # אל תכניס כפילויות (ע"פ en/he)
    en_k, he_k = word_key(en, he)
    for w in words:
        if word_key(w.get("en"), w.get("he")) == (en_k, he_k):
            return jsonify({"ok": False, "error": "המילה כבר קיימת"}), 400

    words.append({"en": en, "he": he, "ok": 0, "bad": 0})
    save_data(d)
    return jsonify({"ok": True})

@app.route("/api/words", methods=["DELETE"])
def api_word_delete():
    """Query: list, en, he"""
    lst = (request.args.get("list") or "").strip()
    en = (request.args.get("en") or "").strip()
    he = (request.args.get("he") or "").strip()
    d = load_data()
    if lst not in d["lists"]:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"}), 404
    en_k, he_k = word_key(en, he)
    before = len(d["lists"][lst])
    d["lists"][lst] = [w for w in d["lists"][lst]
                       if word_key(w.get("en"), w.get("he")) != (en_k, he_k)]
    after = len(d["lists"][lst])
    if after == before:
        return jsonify({"ok": False, "error": "לא נמצאה המילה"}), 404
    save_data(d)
    return jsonify({"ok": True})

# -------- Answers / Stats --------
@app.route("/api/answer", methods=["POST"])
def api_answer():
    """Body: {list, en, he, correct: bool}"""
    data = request.json or {}
    lst = (data.get("list") or "").strip()
    en = (data.get("en") or "").strip()
    he = (data.get("he") or "").strip()
    correct = bool(data.get("correct"))

    d = load_data()
    words = d["lists"].get(lst)
    if words is None:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"}), 404

    en_k, he_k = word_key(en, he)
    found = False
    for w in words:
        if word_key(w.get("en"), w.get("he")) == (en_k, he_k):
            if correct:
                w["ok"] = int(w.get("ok", 0)) + 1
            else:
                w["bad"] = int(w.get("bad", 0)) + 1
            found = True
            break
    if not found:
        return jsonify({"ok": False, "error": "המילה לא קיימת"}), 404

    save_data(d)
    return jsonify({"ok": True})

# -------- Import (Excel/CSV) --------
@app.route("/api/import", methods=["POST"])
def api_import():
    """
    multipart/form-data:
      - list: שם הרשימה
      - file: קובץ .xlsx או .csv
    בקובץ שתי עמודות: EN, HE (ללא כותרות חובה).
    """
    lst = (request.form.get("list") or "").strip()
    if not lst:
        return jsonify({"ok": False, "error": "שם רשימה חסר"}), 400

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "לא נבחר קובץ"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename or "")
    if not filename:
        return jsonify({"ok": False, "error": "שם קובץ לא תקין"}), 400

    ext = filename.rsplit(".", 1)[-1].lower()
    path = os.path.join(UPLOAD_DIR, filename)
    f.save(path)

    words_to_add = []
    try:
        if ext in ("xlsx", "xls"):
            import openpyxl
            wb = openpyxl.load_workbook(path)
            sh = wb.active
            for row in sh.iter_rows(values_only=True):
                if not row: continue
                en = (str(row[0] or "").strip())
                he = (str(row[1] or "").strip()) if len(row) > 1 else ""
                if en and he:
                    words_to_add.append((en, he))
        elif ext == "csv":
            import csv
            with open(path, "r", encoding="utf-8") as fh:
                rdr = csv.reader(fh)
                for row in rdr:
                    if not row: continue
                    en = (str(row[0] or "").strip())
                    he = (str(row[1] or "").strip()) if len(row) > 1 else ""
                    if en and he:
                        words_to_add.append((en, he))
        else:
            return jsonify({"ok": False, "error": "סוג קובץ לא נתמך"}), 400
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

    d = load_data()
    if lst not in d["lists"]:
        d["lists"][lst] = []
    words = d["lists"][lst]

    # הגבלת 15 מילים כולל קיימות
    free_slots = 15 - len(words)
    if free_slots <= 0:
        return jsonify({"ok": False, "error": "הרשימה מלאה (15)"}), 400

    added = 0
    existing = {word_key(w["en"], w["he"]) for w in words}
    for en, he in words_to_add:
        if added >= free_slots:
            break
        k = word_key(en, he)
        if k in existing:
            continue
        words.append({"en": en, "he": he, "ok": 0, "bad": 0})
        existing.add(k)
        added += 1

    save_data(d)
    return jsonify({"ok": True, "added": added, "total": len(words)})

# -------- Quiz helper (client will sort) --------
@app.route("/api/list/<name>/order", methods=["GET"])
def api_quiz_order(name):
    """
    מחזיר את סדר המילים לתרגול מהקשות לקלות.
    ציון קושי: score = ok - 2*bad  (נמוך=קשה)
    """
    d = load_data()
    words = d["lists"].get(name)
    if words is None:
        return jsonify({"ok": False, "error": "הרשימה לא קיימת"}), 404

    def score(w):
        return int(w.get("ok", 0)) - 2 * int(w.get("bad", 0)), int(w.get("ok", 0))

    order = sorted(range(len(words)), key=lambda i: score(words[i]))
    return jsonify({"ok": True, "order": order, "count": len(words)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
