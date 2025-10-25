from flask import Flask, request, jsonify, send_file
import pandas as pd
import json, os, datetime, io

app = Flask(__name__, template_folder="templates", static_folder="static")

DATA_FILE = "words_data.json"
DATE_FILE = "quiz_dates.json"

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
    try:
        data = request.get_json()
        list_name = data.get("list_name")
        date = data.get("date") or datetime.datetime.now().isoformat()
        dates = load_dates()
        dates[list_name] = date
        save_dates(dates)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/last_quiz_dates", methods=["GET"])
def last_quiz_dates():
    return jsonify(load_dates())

@app.route("/api/move_word", methods=["POST"])
def move_word():
    try:
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

        all_data[from_list] = [w for w in all_data[from_list] if w["