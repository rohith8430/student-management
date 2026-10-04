from flask import Flask, render_template, request, redirect
import sqlite3
import datetime

app = Flask(__name__)

# Core subjects for the marks system
SUBJECTS = ["Programming", "Database", "Mathematics", "Computer Networks"]


def get_connection():
    connection = sqlite3.connect("students.db")
    return connection


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Students table (existing structure preserved)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            course TEXT,
            email TEXT
        )
    """)

    # 2. Attendance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """)

    # Unique index to prevent duplicate attendance records for the same student on the same date
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_student_date 
        ON attendance(student_id, date)
    """)

    # 3. Marks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            score REAL NOT NULL,
            max_marks REAL DEFAULT 100,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """)

    # Unique index to prevent duplicate mark records for the same student and subject
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_marks_student_subject 
        ON marks(student_id, subject)
    """)

    connection.commit()
    connection.close()


# Initialize tables on startup
create_tables()


# ==========================================
# STUDENTS ROUTES
# ==========================================

@app.route("/")
def home():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()

    connection.close()

    saved_action = request.args.get("saved")
    return render_template("index.html", students=students, saved_action=saved_action)


@app.route("/add", methods=["POST"])
def add_student():
    name = request.form["name"].strip()
    age = request.form["age"].strip()
    course = request.form["course"].strip()
    email = request.form["email"].strip()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO students (name, age, course, email)
        VALUES (?, ?, ?, ?)
        """,
        (name, age, course, email)
    )

    connection.commit()
    connection.close()

    return redirect("/?saved=added")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        name = request.form["name"].strip()
        age = request.form["age"].strip()
        course = request.form["course"].strip()
        email = request.form["email"].strip()

        cursor.execute(
            """
            UPDATE students
            SET name = ?, age = ?, course = ?, email = ?
            WHERE id = ?
            """,
            (name, age, course, email, id)
        )

        connection.commit()
        connection.close()

        return redirect("/?saved=updated")

    # GET request: fetch student info to pre-fill the form
    cursor.execute("SELECT * FROM students WHERE id = ?", (id,))
    student = cursor.fetchone()
    connection.close()

    if student is None:
        return redirect("/")

    return render_template("edit.html", student=student)


@app.route("/delete/<int:id>")
def delete_student(id):
    connection = get_connection()
    cursor = connection.cursor()

    # Enable foreign keys to cascade or explicitly clean child rows
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("DELETE FROM attendance WHERE student_id = ?", (id,))
    cursor.execute("DELETE FROM marks WHERE student_id = ?", (id,))
    cursor.execute("DELETE FROM students WHERE id = ?", (id,))

    connection.commit()
    connection.close()

    return redirect("/?saved=deleted")


# ==========================================
# ATTENDANCE ROUTES
# ==========================================

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        att_date = request.form.get("date")
        if not att_date:
            att_date = datetime.date.today().isoformat()

        cursor.execute("SELECT id FROM students")
        student_ids = [row[0] for row in cursor.fetchall()]

        for s_id in student_ids:
            status = request.form.get(f"status_{s_id}")
            if status in ["Present", "Absent"]:
                cursor.execute(
                    """
                    INSERT INTO attendance (student_id, date, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(student_id, date) DO UPDATE SET status = excluded.status
                    """,
                    (s_id, att_date, status)
                )

        connection.commit()
        connection.close()

        return redirect(f"/attendance?date={att_date}&saved=1")

    # GET request
    selected_date = request.args.get("date")
    if not selected_date:
        selected_date = datetime.date.today().isoformat()

    cursor.execute("SELECT * FROM students ORDER BY id ASC")
    students = cursor.fetchall()

    # Get marked status for the selected date
    cursor.execute("SELECT student_id, status FROM attendance WHERE date = ?", (selected_date,))
    date_attendance = dict(cursor.fetchall())

    attendance_records = []
    for s in students:
        s_id = s[0]
        status = date_attendance.get(s_id, "Present")  # default to Present
        has_record = s_id in date_attendance
        attendance_records.append({
            "id": s[0],
            "name": s[1],
            "age": s[2],
            "course": s[3],
            "email": s[4],
            "status": status,
            "has_record": has_record
        })

    # Overall Attendance Statistics per student
    cursor.execute("""
        SELECT student_id,
               SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
               SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count,
               COUNT(*) AS total_marked
        FROM attendance
        GROUP BY student_id
    """)
    stats_map = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}

    student_stats = []
    for s in students:
        s_id = s[0]
        p_count, a_count, t_marked = stats_map.get(s_id, (0, 0, 0))
        pct = round((p_count / t_marked * 100), 1) if t_marked > 0 else 0.0
        student_stats.append({
            "id": s_id,
            "name": s[1],
            "course": s[3],
            "present": p_count,
            "absent": a_count,
            "total": t_marked,
            "percentage": pct
        })

    # List of all dates with recorded attendance for quick selector
    cursor.execute("SELECT DISTINCT date FROM attendance ORDER BY date DESC")
    recorded_dates = [row[0] for row in cursor.fetchall()]

    connection.close()
    saved = request.args.get("saved") == "1"

    return render_template(
        "attendance.html",
        attendance_records=attendance_records,
        selected_date=selected_date,
        student_stats=student_stats,
        recorded_dates=recorded_dates,
        saved=saved
    )


# ==========================================
# MARKS ROUTES
# ==========================================

@app.route("/marks")
def marks():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM students ORDER BY id ASC")
    students = cursor.fetchall()

    cursor.execute("SELECT student_id, subject, score FROM marks")
    marks_rows = cursor.fetchall()

    marks_by_student = {}
    for s_id, subject, score in marks_rows:
        if s_id not in marks_by_student:
            marks_by_student[s_id] = {}
        marks_by_student[s_id][subject] = score

    student_marks_list = []
    total_percentages = []

    for s in students:
        s_id = s[0]
        s_marks = marks_by_student.get(s_id, {})

        scores = [s_marks.get(sub) for sub in SUBJECTS]
        valid_scores = [sc for sc in scores if sc is not None]

        if valid_scores:
            total_score = round(sum(valid_scores), 1)
            max_score = len(valid_scores) * 100
            percentage = round((total_score / max_score) * 100, 1)
            total_percentages.append(percentage)

            if percentage >= 90:
                grade = "A+"
            elif percentage >= 80:
                grade = "A"
            elif percentage >= 70:
                grade = "B"
            elif percentage >= 60:
                grade = "C"
            elif percentage >= 50:
                grade = "D"
            else:
                grade = "F"
            status = "Passed" if percentage >= 50 else "Failed"
        else:
            total_score = None
            max_score = None
            percentage = None
            grade = "-"
            status = "Pending"

        student_marks_list.append({
            "id": s[0],
            "name": s[1],
            "course": s[3],
            "scores": s_marks,
            "total": total_score,
            "max_possible": len(SUBJECTS) * 100,
            "percentage": percentage,
            "grade": grade,
            "status": status,
            "has_marks": len(valid_scores) > 0
        })

    class_avg = round(sum(total_percentages) / len(total_percentages), 1) if total_percentages else 0.0
    highest_score = max(total_percentages) if total_percentages else 0.0

    connection.close()
    saved = request.args.get("saved") == "1"

    return render_template(
        "marks.html",
        students=student_marks_list,
        subjects=SUBJECTS,
        class_avg=class_avg,
        highest_score=highest_score,
        saved=saved
    )


@app.route("/marks/edit/<int:id>", methods=["GET", "POST"])
def edit_marks(id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM students WHERE id = ?", (id,))
    student = cursor.fetchone()
    if not student:
        connection.close()
        return redirect("/marks")

    if request.method == "POST":
        for subject in SUBJECTS:
            val = request.form.get(subject, "").strip()
            if val != "":
                try:
                    score = float(val)
                    score = max(0.0, min(100.0, score))  # Keep in 0-100 range
                    cursor.execute(
                        """
                        INSERT INTO marks (student_id, subject, score, max_marks)
                        VALUES (?, ?, ?, 100)
                        ON CONFLICT(student_id, subject) DO UPDATE SET score = excluded.score
                        """,
                        (id, subject, score)
                    )
                except ValueError:
                    pass

        connection.commit()
        connection.close()

        return redirect("/marks?saved=1")

    # GET request: fetch current scores for student
    cursor.execute("SELECT subject, score FROM marks WHERE student_id = ?", (id,))
    current_marks = dict(cursor.fetchall())

    connection.close()

    return render_template(
        "edit_marks.html",
        student=student,
        subjects=SUBJECTS,
        current_marks=current_marks
    )


if __name__ == "__main__":
    app.run(debug=True)