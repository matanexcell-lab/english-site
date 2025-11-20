import os
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, send_file
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from io import BytesIO

# ---------------------------------------------------------
# הגדרות בסיסיות
# ---------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://matan_nb_user:Qzcukb3uonnqU3wgDxKyzkxeEaT83PJp@dpg-d40u1m7gi27c73d0oorg-a.oregon-postgres.render.com/matan_nb"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
Session = scoped_session(sessionmaker(bind=engine, autoflush=False))

Base = declarative_base()

# ---------------------------------------------------------
# מודלים למסד
# ---------------------------------------------------------

class WordList(Base):
    __tablename__ = "word_lists"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    last_quiz = Column(String, nullable=True)

    words = relationship("Word", cascade="all, delete-orphan")

class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("word_lists.id"))
    en = Column(String)
    he = Column(String)
    correct = Column(Integer, default=0)
    wrong = Column(Integer, default=0)


# יצירת טבלאות אם לא קיימות
Base.metadata.create_all(engine)

app = Flask(__name__)

def get_db():
    return Session()

# ---------------------------------------------------------
# API: GET כל הרשימות
# ---------------------------------------------------------

@app.route("/api/lists")
def api_lists():
    db = get_db()
    lists = db.query(WordList).all()

    result = {}
    for lst in lists:
        result[lst.name] = [
            {
                "en": w.en,
                "he": w.he,
                "correct": w.correct,
                "wrong": w.wrong
            }
            for w in lst.words
        ]

    return jsonify(result)

# ---------------------------------------------------------
# API: POST שמירת רשימה
# ---------------------------------------------------------

@app.route("/api/lists", methods=["POST"])
def api_save_list():
    data = request.json
    name = data.get("name")
    words = data.get("words", [])

    db = get_db()
    lst = db.query(WordList).filter_by(name=name).first()

    if not lst:
        lst = WordList(name=name)
        db.add(lst)
        db.commit()

    # מוחקים מילים קיימות
    db.query(Word).filter_by(list_id=lst.id).delete()

    # מוסיפים מילים חדשות
    for w in words:
        db.add(Word(
            list_id=lst.id,
            en=w["en"],
            he=w["he"],
            correct=w.get("correct", 0),
            wrong=w.get("wrong", 0)
        ))

    db.commit()
    return jsonify({"ok": True})

# ---------------------------------------------------------
# API: תאריכי חידון
# ---------------------------------------------------------

@app.route("/api/last_quiz_dates")
def api_last_quiz_dates():
    db = get_db()
    lists = db.query(WordList).all()
    return jsonify({l.name: l.last_quiz for l in lists})

@app.route("/api/update_quiz_date", methods=["POST"])
def api_update_quiz_date():
    data = request.json
    list_name = data["list_name"]

    db = get_db()
    lst = db.query(WordList).filter_by(name=list_name).first()

    if lst:
        lst.last_quiz = datetime.now().strftime("%d/%m/%Y %H:%M")
        db.commit()

    return jsonify({"ok": True})

# ---------------------------------------------------------
# API: ייבוא קובץ Excel
# ---------------------------------------------------------

@app.route("/api/import_excel", methods=["POST"])
def api_import_excel():
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "לא נשלח קובץ"})

    file = request.files["file"]
    df = pd.read_excel(file)

    if df.empty:
        return jsonify({"ok": False, "message": "קובץ ריק"})

    col_map = {c.lower(): c for c in df.columns}

    if "list" not in col_map:
        df["list"] = "Default"

    db = get_db()

    # מוחקים הכל
    db.query(Word).delete()
    db.query(WordList).delete()
    db.commit()

    grouped = df.groupby("list")

    for list_name, group in grouped:
        wl = WordList(name=str(list_name))
        db.add(wl)
        db.commit()

        for _, row in group.iterrows():
            db.add(Word(
                list_id=wl.id,
                en=str(row.get(col_map.get("en"), "")),
                he=str(row.get(col_map.get("he"), "")),
                correct=int(row.get(col_map.get("correct"), 0)),
                wrong=int(row.get(col_map.get("wrong"), 0)),
            ))

        db.commit()

    return jsonify({"ok": True, "message": "הנתונים נטענו בהצלחה!"})

# ---------------------------------------------------------
# API: הורד את כל הנתונים — עובד 100%
# ---------------------------------------------------------

@app.route("/api/download_excel")
def api_download_excel():

    db = get_db()
    lists = db.query(WordList).all()

    rows = []
    for lst in lists:
        for w in lst.words:
            rows.append({
                "list": lst.name,
                "en": w.en,
                "he": w.he,
                "correct": w.correct,
                "wrong": w.wrong,
                "last_quiz": lst.last_quiz
            })

    df = pd.DataFrame(rows)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="all_words.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------------------------------------------------
# הפעלת האתר
# ---------------------------------------------------------

@app.route("/")
def home():
    return send_file("templates/index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)