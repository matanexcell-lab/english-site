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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
