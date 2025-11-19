@app.route("/api/import_excel", methods=["POST"])
def import_excel():
    """
    מייבא קובץ אקסל ומחליף את כל הנתונים במסד.
    אם אין עמודה "list" — ניצור רשימה אחת בשם Default.
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

    # מנרמלים שמות עמודות
    col_map = {c.lower(): c for c in df.columns}

    has_list = "list" in col_map

    # במקרה שאין עמודת list — הכל ברשימה אחת
    if not has_list:
        df["list"] = "Default"
        col_map["list"] = "list"

    # בונים מבנה { list_name: rows }
    grouped = {}
    for _, row in df.iterrows():
        list_name = str(row[col_map["list"]]).strip()
        if not list_name:
            list_name = "Default"
        grouped.setdefault(list_name, []).append(row)

    # כותבים למסד הנתונים
    with get_session() as db:
        db.query(Word).delete()
        db.query(WordList).delete()
        db.flush()

        for list_name, rows in grouped.items():
            wl = WordList(name=list_name)
            db.add(wl)
            db.flush()

            # ניסיון לקרוא last_quiz מתוך עמודה אם קיימת
            if "last_quiz" in col_map:
                for r in rows:
                    val = r[col_map["last_quiz"]]
                    if pd.notna(val) and str(val).strip():
                        wl.last_quiz = str(val).strip()
                        break

            # קריאת המילים
            for r in rows:
                en = str(r.get(col_map.get("en", ""), "")).strip()
                he = str(r.get(col_map.get("he", ""), "")).strip()
                if not en or not he:
                    continue

                correct = int(r[col_map["correct"]]) if "correct" in col_map and pd.notna(r[col_map["correct"]]) else 0
                wrong = int(r[col_map["wrong"]]) if "wrong" in col_map and pd.notna(r[col_map["wrong"]]) else 0

                db.add(Word(
                    list_id=wl.id,
                    en=en,
                    he=he,
                    correct=correct,
                    wrong=wrong
                ))

    return jsonify({"ok": True, "message": "הקובץ נקלט בהצלחה! הנתונים התעדכנו."})