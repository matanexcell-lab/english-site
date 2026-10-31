import os
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from io import BytesIO

# ---------------------------------------------------------
# הגדרות בסיסיות
# ---------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in environment variables")

# כמה ימים בלי תרגול עד שמילה "ידועה" חוזרת לחידון והספירה שלה מתאפסת
REVIEW_DAYS = 30
DATE_FMT = "%Y-%m-%d"

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


@app.teardown_appcontext
def remove_session(exc=None):
    # סוגר את החיבור למסד בסוף כל בקשה
    Session.remove()


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
    last_seen = Column(String, nullable=True)   # YYYY-MM-DD – הפעם האחרונה שהמילה נשאלה


# יצירת טבלאות אם לא קיימות
Base.metadata.create_all(engine)

# הוספת העמודה last_seen לטבלה קיימת (create_all לא מוסיף עמודות)
# קודם סוגרים חיבורים "תקועים" של הגרסה הקודמת, שאחרת חוסמים את השינוי בטבלה
with engine.begin() as conn:
    conn.execute(text("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND state LIKE 'idle in transaction%'
          AND pid <> pg_backend_pid()
    """))

with engine.begin() as conn:
    conn.execute(text("SET LOCAL lock_timeout = '15s'"))
    conn.execute(text("ALTER TABLE words ADD COLUMN IF NOT EXISTS last_seen VARCHAR"))


def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], DATE_FMT)
    except (ValueError, TypeError):
        return None


def clean_value(v):
    """ממיר NaN של pandas ל-None"""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ---------------------------------------------------------
# API: קבלת רשימות (כולל איפוס חודשי)
# ---------------------------------------------------------

@app.route("/api/lists")
def api_lists():
    try:
        db = get_db()
        lists = db.query(WordList).all()

        now = datetime.now()
        today_str = now.strftime(DATE_FMT)
        changed = False

        result = {}
        for lst in lists:
            for w in lst.words:
                seen = parse_date(w.last_seen)

                if seen is None:
                    # מילים ישנות בלי תאריך – מתחילים לספור מהיום
                    w.last_seen = today_str
                    changed = True

                elif (w.correct or 0) > (w.wrong or 0) and now - seen >= timedelta(days=REVIEW_DAYS):
                    # מילה "ידועה" שלא תורגלה חודש – חוזרת לחידון מאפס
                    w.correct = 0
                    w.wrong = 0
                    changed = True

            result[lst.name] = [
                {
                    "en": w.en,
                    "he": w.he,
                    "correct": w.correct,
                    "wrong": w.wrong,
                    "last_seen": w.last_seen
                }
                for w in lst.words
            ]

        if changed:
            db.commit()

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

        today_str = datetime.now().strftime(DATE_FMT)
        for w in words:
            db.add(Word(
                list_id=lst.id,
                en=w["en"],
                he=w["he"],
                correct=w.get("correct", 0),
                wrong=w.get("wrong", 0),
                last_seen=w.get("last_seen") or today_str
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
            col_map["list"] = "list"

        db = get_db()

        db.query(Word).delete()
        db.query(WordList).delete()
        db.commit()

        today_str = datetime.now().strftime(DATE_FMT)
        grouped = df.groupby(col_map["list"])

        for list_name, group in grouped:
            wl = WordList(name=str(list_name))
            db.add(wl)
            db.commit()

            for _, row in group.iterrows():
                def val(key, default=None):
                    col = col_map.get(key)
                    return clean_value(row.get(col)) if col else default

                seen = val("last_seen")
                seen_date = parse_date(seen) if seen is not None else None

                db.add(Word(
                    list_id=wl.id,
                    en=str(val("en", "") or ""),
                    he=str(val("he", "") or ""),
                    correct=int(val("correct", 0) or 0),
                    wrong=int(val("wrong", 0) or 0),
                    last_seen=seen_date.strftime(DATE_FMT) if seen_date else today_str
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
                "last_seen": w.last_seen,
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
