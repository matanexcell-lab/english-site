from flask import Flask, request, jsonify, send_file
import pandas as pd
import os

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    return send_file("templates/index.html")

@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    print("📥 התקבלה בקשה לייבוא אקסל!")  # נבדוק אם בכלל הגענו לפה

    if "file" not in request.files:
        print("⚠️ לא נמצא קובץ בבקשה")
        return jsonify({"ok": False, "message": "לא נשלח קובץ"})

    file = request.files["file"]
    if file.filename == "":
        print("⚠️ שם הקובץ ריק")
        return jsonify({"ok": False, "message": "שם הקובץ ריק"})

    try:
        print(f"📂 מנסה לקרוא את הקובץ: {file.filename}")
        df = pd.read_excel(file)
        print(f"✅ נקראו {len(df)} שורות")
        return jsonify({"ok": True, "message": f"הקובץ נקלט בהצלחה ({len(df)} שורות)."})
    except Exception as e:
        print("❌ שגיאה בקריאת הקובץ:", e)
        return jsonify({"ok": False, "message": f"שגיאה בקריאת הקובץ: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)