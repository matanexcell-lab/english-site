import os
import io
import json
import datetime

from flask import Flask, request, jsonify, send_file
import pandas as pd

from sqlalchemy import (
    create_engine, Column, Integer, String, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, relationship
from contextlib import contextmanager


# =====================================================
# 🔧 הגדרות בסיסיות + חיבור למסד נתונים (PostgreSQL)
# =====================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # ⭐ רק ברירת מחדל — ב־Render זה יעודכן אוטומטית
    "postgresql://matan_nb_user:Qzcukb3uonnqU3wgDxKyzkxeEaT83PJp@dpg-d40u1m7gi27c73d0oorg-a/matan_nb"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
Session = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()

app = Flask(__name__, template_folder="templates", static_folder="static")


# =====================================================
# 📦 מודלים למסד הנתונים
# =====================================================

class WordList(Base):
    __tablename__ = "word_lists"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    last_quiz = Column(String, nullable=True)

    words = relationship("Word", back_populates="list", cascade="all, delete-orphan")


class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("word_lists.id", ondelete="CASCADE"), nullable=False)
    en = Column(String, nullable=False)
    he = Column(String, nullable=False)
    correct = Column(Integer, default=0)
    wrong = Column(Integer, default=0)

    list = relationship("WordList", back_populates="words")


Base.metadata.create_all(bind=engine)


# =====================================================
# 🏦 כלי ניהול Session
# =====================================================

@contextmanager
def get_session():
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =====================================================
# 🛈 מיגרציה חד פעמית מה־JSON הישן למסד הנתונים
# =====================================================

DATA_FILE = "words_data.json"
DATE_FILE = "quiz_dates.json"


def load_old_json_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if os.path.exists(DATE_FILE):
        with open(DATE_FILE, "r", encoding="utf-8") as f:
            dates = json.load(f)
    else:
        dates = {}

    return data, dates


def migrate_from_json_if_needed():
    """מריץ מיגרציה פעם ראשונה בלבד."""
    with get_session() as db:
        if db.query(WordList).count() > 0:
            return  # יש נתונים → לא לייבא JSON

    data, dates = load_old_json_data()

    if not data:
        return

    with get_session() as db:
        for list_name, words in data.items():
            wl = WordList(name=list_name, last_quiz=dates.get(list_name))
            db.add(wl)
            db.flush()

            for w in words:
                db.add(Word(
                    list_id=wl.id,
                    en=w.get("en", "").strip(),
                    he=w.get("he", "").strip(),
                    correct=int(w.get("correct", 0) or 0),
                    wrong=int(w.get("wrong", 0) or 0)
                ))


migrate_from_json_if_needed()


# =====================================================
# 🌐 ראוטים — צד שרת
# =====================================================

@app.route("/")
def home():
    return send_file("templates/index.html")


# -------- קבלת רשימות --------

@app.route("/api/lists", methods=["GET"])
def get_lists():
    result = {}
    with get_session() as db:
        lists = db.query(WordList).all()
        for wl in lists:
            result[wl.name] = [
                {
                    "en": w.en,
                    "he": w.he,
                    "correct": w.correct,
                    "wrong": w.wrong
                }
                for w in wl.words
            ]
    return jsonify(result)


@app.route("/api/lists", methods=["POST"])
def save_list():
    body = request.json
    list_name = body["name"]
    words = body.get("words", [])

    with get_session() as db:
        wl = db.query(WordList).filter_by(name=list_name).first()

        if wl is None:
            wl = WordList(name=list_name)
            db.add(wl)
            db.flush()

        db.query(Word).filter_by(list_id=wl.id).delete()

        for w in words:
            db.add(Word(
                list_id=wl.id,
                en=w["en"],
                he=w["he"],
                correct=w.get("correct", 0),
                wrong=w.get("wrong", 0)
            ))

    return jsonify({"ok": True})


# -------- תאריך חידון --------

@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    data = request.json
    list_name = data["list_name"]

    date_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    with get_session() as db:
        wl = db.query(WordList).filter_by(name=list_name).first()
        if wl:
            wl.last_quiz = date_str

    return jsonify({"ok": True})


@app.route("/api/last_quiz_dates", methods=["GET"])
def last_quiz_dates():
    result = {}
    with get_session() as db:
        for wl in db.query(WordList).all():
            if wl.last_quiz:
                result[wl.name] = wl.last_quiz
    return jsonify(result)


# -------- מעבר מילה --------

@app.route("/api/move_word", methods=["POST"])
def move_word():
    data = request.json
    from_list = data["from_list"]
    to_list = data["to_list"]
    word_en = data["word"]

    with get_session() as db:
        src = db.query(WordList).filter_by(name=from_list).first()
        dst = db.query(WordList).filter_by(name=to_list).first()

        if not src or not dst:
            return jsonify({"ok": False, "message": "רשימה לא קיימת"})

        word = db.query(Word).filter_by(list_id=src.id, en=word_en).first()
        if not word:
            return jsonify({"ok": False, "message": "המילה לא נמצאה"})

        exists = db.query(Word).filter_by(list_id=dst.id, en=word_en).first()

        if exists:
            exists.correct += word.correct
            exists.wrong += word.wrong
            db.delete(word)
        else:
            word.list_id = dst.id

    return jsonify({"ok": True})


# =====================================================
# 📥 ייבוא אקסל — תואם לקובץ שלך (עברית + אנגלית)
# =====================================================

@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    """
    מייבא אקסל → מחליף את כל הנתונים במסד הנתונים
    תומך בעמודות:
      English, עברית, נכון, שגוי, שם רשימה, תאריך חידון
    """

    if "file" not in request.files:
        return jsonify({"ok": False, "message": "לא נשלח קובץ"})

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "message": "שם הקובץ ריק"})

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

    if df.empty:
        return jsonify({"ok": False, "message": "קובץ ריק"})

    # 🟦 מיפוי עמודות מהקובץ שלך
    rename_map = {
        "words in english": "en",
        "תרגום בעברית": "he",
        "כמה פעמים ענית נכון": "correct",
        "כמה פעמים ענית לא נכון": "wrong",
        "שם הרשימה": "list",
        "תאריך אחרון חידון": "last_quiz",
    }

    normalized_cols = {c.lower(): c for c in df.columns}

    # מחליף שמות לעמודות הנכונות
    for lower, original in normalized_cols.items():
        if lower in rename_map:
            df.rename(columns={original: rename_map[lower]}, inplace=True)

    # חובה שיהיו 3 עמודות
    for col in ("en", "he", "list"):
        if col not in df.columns:
            return jsonify({"ok": False, "message": f"חסרה עמודה: {col}"}), 400

    groups = {}
    for _, row in df.iterrows():
        list_name = str(row.get("list", "Default")).strip()
        groups.setdefault(list_name, []).append(row)

    with get_session() as db:
        db.query(Word).delete()
        db.query(WordList).delete()
        db.flush()

        for list_name, rows in groups.items():
            wl = WordList(name=list_name)
            db.add(wl)
            db.flush()

            for r in rows:
                en = str(r.get("en", "")).strip()
                he = str(r.get("he", "")).strip()
                if not en or not he:
                    continue

                correct = int(r.get("correct", 0) or 0)
                wrong = int(r.get("wrong", 0) or 0)
                wl.last_quiz = str(r.get("last_quiz", "")).strip() or wl.last_quiz

                db.add(
                    Word(
                        list_id=wl.id,
                        en=en,
                        he=he,
                        correct=correct,
                        wrong=wrong,
                    )
                )

    return jsonify({"ok": True, "message": "הקובץ נקלט בהצלחה!"})


# =====================================================
# הרצה מקומית
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)