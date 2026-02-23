import os
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, send_file
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from io import BytesIO

# ---------------------------------------------------------
# הגדרות בסיסיות
# ---------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in environment variables")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True
)

Session = scoped_session(sessionmaker(bind=engine, autoflush=False))
Base = declarative_base()

app = Flask(__name__)


def get_db():
    return Session()


# ---------------------------------------------------------
# מודלים
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

# ---------------------------------------------------------
# API: קבלת רשימות
# ---------------------------------------------------------

@app.route("/api/lists")
def api_lists():
    try:
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

    except SQLAlchemyError as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------
# API: שמירת רשימה
# ---------------------------------------------------------

@app.route("/api/lists", methods=["POST"])
def api_save_list():
    try:
        data = request.json
        name = data.get("name")
        words = data.get("words", [])

        db = get_db()
        lst = db.query(WordList).filter_by(name=name).first()

        if not lst:
            lst = WordList(name=name)
            db.add(lst)
            db.commit()

        db.query(Word).filter_by(list_id=lst.id).delete()

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

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
# API: ייבוא Excel
# ---------------------------------------------------------

@app.route("/api/import_excel", methods=["POST"])
def api_import_excel():
    try:
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
                    correct=int(row.get(col_map.get("correct"), 0) or 0),
                    wrong=int(row.get(col_map.get("wrong"), 0) or 0),
                ))

            db.commit()

        return jsonify({"ok": True, "message": "הנתונים נטענו בהצלחה!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------
# API: הורדת Excel
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
# עמוד ראשי
# ---------------------------------------------------------

@app.route("/")
def home():
    return send_file("templates/index.html")


# ---------------------------------------------------------
# Gunicorn משתמש בזה – אין צורך ב-app.run()
# ---------------------------------------------------------