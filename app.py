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
    last_quiz = Column(String, nullable=True)  # נשמור כמחרוזת (כמו שהאתר מציג)

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
    """אם אין רשימות במסד, נייבא מה־JSON פעם אחת."""
    with get_session() as db:
        count = db.query(WordList).count()
        if count > 0:
            return  # כבר קיימים נתונים, לא צריך מיגרציה

    data, dates = load_old_json_data()
    if not data:
        return

    with get_session() as db:
        for list_name, words in data.items():
            wl = WordList(
                name=list_name,
                last_quiz=dates.get(list_name)
            )
            db.add(wl)
            db.flush()  # כדי לקבל wl.id

            for w in words:
                db.add(
                    Word(
                        list_id=wl.id,
                        en=w.get("en", "").strip(),
                        he=w.get("he", "").strip(),
                        correct=int(w.get("correct", 0) or 0),
                        wrong=int(w.get("wrong", 0) or 0),
                    )
                )


# להריץ את המיגרציה בזמן עליית האפליקציה
migrate_from_json_if_needed()

# =====================================================
# 🌐 ראוטים
# =====================================================

@app.route("/")
def home():
    return send_file("templates/index.html")


# -------- רשימות ומילים --------

@app.route("/api/lists", methods=["GET"])
def get_lists():
    """החזרת כל הרשימות וההיסטוריה של המילים במבנה שה־JS כבר מכיר."""
    result = {}
    with get_session() as db:
        lists = db.query(WordList).all()
        for wl in lists:
            words = []
            for w in wl.words:
                words.append({
                    "en": w.en,
                    "he": w.he,
                    "correct": w.correct or 0,
                    "wrong": w.wrong or 0,
                })
            result[wl.name] = words
    return jsonify(result)


@app.route("/api/lists", methods=["POST"])
def save_list():
    """
    ה־Frontend שולח name + words (מערך של מילים).
    אנחנו מחליפים את כל המילים של הרשימה.
    """
    body = request.json
    if not body or "name" not in body:
        return jsonify({"error": "missing name"}), 400

    list_name = body["name"]
    words_data = body.get("words", [])

    with get_session() as db:
        wl = db.query(WordList).filter_by(name=list_name).first()
        if wl is None:
            wl = WordList(name=list_name)
            db.add(wl)
            db.flush()

        # מוחקים מילים ישנות של הרשימה
        db.query(Word).filter_by(list_id=wl.id).delete()

        # מוסיפים את המילים החדשות
        for w in words_data:
            en = (w.get("en") or "").strip()
            he = (w.get("he") or "").strip()
            if not en or not he:
                continue
            correct = int(w.get("correct", 0) or 0)
            wrong = int(w.get("wrong", 0) or 0)
            db.add(Word(list_id=wl.id, en=en, he=he, correct=correct, wrong=wrong))

    return jsonify({"ok": True})


# -------- תאריכי חידון --------

@app.route("/api/update_quiz_date", methods=["POST"])
def update_quiz_date():
    """
    מעדכן תאריך אחרון שנבחנת לרשימה מסוימת.
    ה־Frontend שולח: { "list_name": "...", "date": "...אופציונלי..." }
    """
    try:
        data = request.get_json() or {}
        list_name = data.get("list_name")
        if not list_name:
            return jsonify({"ok": False, "error": "missing list_name"}), 400

        date_str = data.get("date")
        if not date_str:
            # ברירת מחדל: התאריך המקומי (כמו שהיה בצד לקוח)
            date_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

        with get_session() as db:
            wl = db.query(WordList).filter_by(name=list_name).first()
            if wl is None:
                wl = WordList(name=list_name)
                db.add(wl)
                db.flush()

            wl.last_quiz = date_str

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/last_quiz_dates", methods=["GET"])
def last_quiz_dates():
    """
    מחזיר מילון: { list_name: last_quiz_string }
    """
    result = {}
    with get_session() as db:
        lists = db.query(WordList).all()
        for wl in lists:
            if wl.last_quiz:
                result[wl.name] = wl.last_quiz
    return jsonify(result)


# -------- מעבר מילה מרשימה לרשימה --------

@app.route("/api/move_word", methods=["POST"])
def move_word():
    data = request.json or {}
    from_list = data.get("from_list")
    to_list = data.get("to_list")
    word_en = data.get("word")

    if not from_list or not to_list or not word_en:
        return jsonify({"ok": False, "message": "חסרים נתונים לביצוע ההעברה."}), 400

    with get_session() as db:
        src = db.query(WordList).filter_by(name=from_list).first()
        dst = db.query(WordList).filter_by(name=to_list).first()

        if not src or not dst:
            return jsonify({"ok": False, "message": "רשימה לא קיימת."})

        word = db.query(Word).filter_by(list_id=src.id, en=word_en).first()
        if not word:
            return jsonify({"ok": False, "message": "המילה לא נמצאה ברשימת המקור."})

        # אם כבר קיימת מילה כזאת ברשימת היעד – נאחד סטטיסטיקות
        existing = db.query(Word).filter_by(list_id=dst.id, en=word_en).first()
        if existing:
            existing.correct = (existing.correct or 0) + (word.correct or 0)
            existing.wrong = (existing.wrong or 0) + (word.wrong or 0)
            db.delete(word)
        else:
            word.list_id = dst.id

    return jsonify({"ok": True, "message": "המילה הועברה בהצלחה."})


# -------- ייבוא / ייצוא Excel --------

@app.route("/api/download_excel", methods=["GET"])
def download_excel():
    """
    מייצא את כל המילים לקובץ אקסל.
    עמודות: list, en, he, correct, wrong, last_quiz
    """
    rows = []
    with get_session() as db:
        lists = db.query(WordList).all()
        for wl in lists:
            for w in wl.words:
                rows.append({
                    "list": wl.name,
                    "en": w.en,
                    "he": w.he,
                    "correct": w.correct or 0,
                    "wrong": w.wrong or 0,
                    "last_quiz": wl.last_quiz or "",
                })

    if not rows:
        rows.append({
            "list": "",
            "en": "",
            "he": "",
            "correct": 0,
            "wrong": 0,
            "last_quiz": "",
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="words")
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="all_words_export.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    """
    מייבא קובץ אקסל ומחליף את כל הנתונים במסד.
    תומך בשני פורמטים:
      חובה: list, en, he
      אופציונלי: correct, wrong, last_quiz
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "לא נשלח קובץ"})

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "message": "שם הקובץ ריק"})

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"ok": False, "message": f"שגיאה בקריאת הקובץ: {e}"})

    if df.empty:
        return jsonify({"ok": False, "message": "הקובץ ריק"})

    # ננרמל שמות עמודות (lower)
    col_map = {c.lower(): c for c in df.columns}

    for required in ("list", "en", "he"):
        if required not in col_map:
            return jsonify({"ok": False, "message": f"חסרה עמודה: {required}"}), 400

    # בונים מבנה: { list_name: [rows...] }
    grouped = {}
    for _, row in df.iterrows():
        list_name = str(row[col_map["list"]]).strip()
        if not list_name:
            continue
        grouped.setdefault(list_name, []).append(row)

    with get_session() as db:
        # מוחקים הכל ובונים מחדש
        db.query(Word).delete()
        db.query(WordList).delete()
        db.flush()

        for list_name, rows in grouped.items():
            wl = WordList(name=list_name)

            # last_quiz (אם יש עמודה כזאת)
            if "last_quiz" in col_map:
                for r in rows:
                    val = r[col_map["last_quiz"]]
                    if pd.notna(val) and str(val).strip():
                        wl.last_quiz = str(val).strip()
                        break

            db.add(wl)
            db.flush()

            for r in rows:
                en = str(r[col_map["en"]]).strip()
                he = str(r[col_map["he"]]).strip()
                if not en or not he:
                    continue

                correct = 0
                wrong = 0
                if "correct" in col_map:
                    val = r[col_map["correct"]]
                    if pd.notna(val):
                        correct = int(val)
                if "wrong" in col_map:
                    val = r[col_map["wrong"]]
                    if pd.notna(val):
                        wrong = int(val)

                db.add(
                    Word(
                        list_id=wl.id,
                        en=en,
                        he=he,
                        correct=correct,
                        wrong=wrong,
                    )
                )

    return jsonify({"ok": True, "message": "הקובץ נקלט בהצלחה, והנתונים עודכנו."})


# =====================================================
# הרצה מקומית (לא רלוונטי ל־Render אבל לא מזיק)
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)