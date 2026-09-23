from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google import genai
from google.genai import types
import os
import json
from datetime import datetime


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "ecotrack-secret-key"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "ecotrack.db")

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "uploads"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table, column):
    columns = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(row["name"] == column for row in columns)


def create_database():

    conn = get_db()

    # USERS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Add role if old database does not have it
    if not column_exists(conn, "users", "role"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'citizen'"
        )

    conn.execute("""
        UPDATE users
        SET role = 'citizen'
        WHERE role IS NULL OR role = ''
    """)

    # REPORTS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_username TEXT NOT NULL,
            message TEXT NOT NULL,
            location TEXT,
            image_filename TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT
        )
    """)

    # Add columns if old reports table exists
    if not column_exists(conn, "reports", "location"):
        conn.execute(
            "ALTER TABLE reports ADD COLUMN location TEXT"
        )

    if not column_exists(conn, "reports", "image_filename"):
        conn.execute(
            "ALTER TABLE reports ADD COLUMN image_filename TEXT"
        )

    if not column_exists(conn, "reports", "status"):
        conn.execute(
            "ALTER TABLE reports ADD COLUMN status TEXT DEFAULT 'Pending'"
        )

    if not column_exists(conn, "reports", "created_at"):
        conn.execute(
            "ALTER TABLE reports ADD COLUMN created_at TEXT"
        )

    conn.commit()
    conn.close()


# IMPORTANT:
# This runs even when Render starts Flask using Gunicorn.
create_database()


# ---------------- WASTE DATA ----------------

BIN_INFO = {

    "Green": {
        "description": "Biodegradable and wet waste.",
        "examples": "Food waste, vegetable peels, fruit peels, leaves"
    },

    "Blue": {
        "description": "Dry and recyclable waste.",
        "examples": "Paper, cardboard, plastic bottles, metal cans"
    },

    "Yellow": {
        "description": "Special waste that needs careful disposal.",
        "examples": "Batteries, medicines, medical or chemical waste"
    },

    "Black": {
        "description": "General non-recyclable waste.",
        "examples": "Diapers, tissues, thermocol and other non-recyclable waste"
    }
}


WASTE_DATA = {

    "banana peel": {
        "type": "Biodegradable waste",
        "hazard": 5,
        "bin": "Green",
        "guidance": "Put it in the green bin. It can be composted."
    },

    "food waste": {
        "type": "Biodegradable waste",
        "hazard": 5,
        "bin": "Green",
        "guidance": "Put food waste in the green bin."
    },

    "paper": {
        "type": "Recyclable waste",
        "hazard": 5,
        "bin": "Blue",
        "guidance": "Keep the paper dry and put it in the blue bin."
    },

    "cardboard": {
        "type": "Recyclable waste",
        "hazard": 5,
        "bin": "Blue",
        "guidance": "Flatten the cardboard and put it in the blue bin."
    },

    "plastic bottle": {
        "type": "Recyclable waste",
        "hazard": 15,
        "bin": "Blue",
        "guidance": "Empty and rinse the bottle before recycling."
    },

    "plastic": {
        "type": "Recyclable waste",
        "hazard": 20,
        "bin": "Blue",
        "guidance": "Separate recyclable plastic and put it in the blue bin."
    },

    "metal can": {
        "type": "Recyclable waste",
        "hazard": 10,
        "bin": "Blue",
        "guidance": "Rinse the can and place it in the blue bin."
    },

    "glass bottle": {
        "type": "Recyclable waste",
        "hazard": 15,
        "bin": "Blue",
        "guidance": "Handle carefully and place it with recyclable glass."
    },

    "battery": {
        "type": "Hazardous waste",
        "hazard": 90,
        "bin": "Yellow",
        "guidance": "Do not throw batteries into normal waste."
    },

    "paint": {
        "type": "Special waste",
        "hazard": 85,
        "bin": "Yellow",
        "guidance": "Follow local hazardous-waste collection instructions."
    },

    "medicine": {
        "type": "Special waste",
        "hazard": 80,
        "bin": "Yellow",
        "guidance": "Use an appropriate medicine collection facility."
    },

    "diaper": {
        "type": "General waste",
        "hazard": 40,
        "bin": "Black",
        "guidance": "Wrap properly and place it in the black bin."
    },

    "tissue": {
        "type": "General waste",
        "hazard": 20,
        "bin": "Black",
        "guidance": "Used tissues should generally go into the black bin."
    },

    "thermocol": {
        "type": "Non-recyclable waste",
        "hazard": 30,
        "bin": "Black",
        "guidance": "Place thermocol in the black bin where locally appropriate."
    }
}


# ---------------- LOGIN / REGISTER ----------------

@app.route("/")
def index():

    if "username" in session:
        return redirect(url_for("home"))

    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]

        if role not in ["citizen", "worker"]:
            return "Invalid role selected."

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO users
                (username, password, role)
                VALUES (?, ?, ?)
                """,
                (username, hashed_password, role)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Username already exists!"


    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            """
            SELECT * FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect(url_for("home"))

        return "Invalid username or password!"

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# ---------------- HOME ----------------

@app.route("/home")
def home():

    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "worker":

        return render_template(
            "worker.html",
            username=session["username"]
        )

    return render_template(
        "home.html",
        username=session["username"]
    )


# ---------------- BINS ----------------

@app.route("/bins")
def bins():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template(
        "bins.html",
        bins=BIN_INFO
    )


# ---------------- WASTE HELPER ----------------

@app.route("/helper", methods=["GET", "POST"])
def helper():

    if "username" not in session:
        return redirect(url_for("login"))

    result = None

    if request.method == "POST":

        waste = request.form["waste"].strip().lower()

        if waste in WASTE_DATA:

            result = WASTE_DATA[waste]

        else:

            result = {
                "type": "Unknown waste",
                "hazard": "Unknown",
                "bin": "Cannot determine",
                "guidance": "This item is not currently in our database."
            }

    return render_template(
        "helper.html",
        result=result
    )


# ---------------- AI PHOTO DETECTION ----------------

@app.route("/photo", methods=["POST"])
def photo():

    if "username" not in session:
        return redirect(url_for("login"))

    uploaded_file = request.files.get("photo")

    if not uploaded_file or uploaded_file.filename == "":
        return "Please select an image."

    try:

        image_bytes = uploaded_file.read()

        api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception("GEMINI_API_KEY is not configured.")

        client = genai.Client(api_key=api_key)

        prompt = """
        Identify the main waste item in this image.

        Return ONLY valid JSON.

        Format:

        {
          "waste": "name of waste",
          "type": "waste type",
          "hazard": 0,
          "bin": "Green",
          "guidance": "short disposal guidance"
        }

        Rules:

        bin MUST be one of:
        Green
        Blue
        Yellow
        Black

        hazard MUST be a number between 0 and 100.
        """

        response = client.models.generate_content(

            model="gemini-3.8-flash",

            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=uploaded_file.mimetype
                ),
                prompt
            ],

            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        text = response.text.strip()

        text = text.replace(
            "```json",
            ""
        ).replace(
            "```",
            ""
        ).strip()

        result = json.loads(text)

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result=result
        )

    except Exception as e:

        print("AI ERROR:", e)

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result={
                "waste": "Could not identify",
                "type": "Unknown",
                "hazard": "Unknown",
                "bin": "Cannot determine",
                "guidance": "AI detection failed. Please try another clear image."
            }
        )


# ---------------- REPORT ----------------

@app.route("/report", methods=["GET", "POST"])
def report():

    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "citizen":
        return redirect(url_for("home"))

    if request.method == "POST":

        message = request.form["message"].strip()
        location = request.form["location"].strip()

        image = request.files.get("image")

        image_filename = None

        if image and image.filename:

            original_name = secure_filename(
                image.filename
            )

            timestamp = datetime.now().strftime(
                "%Y%m%d%H%M%S"
            )

            image_filename = (
                timestamp
                + "_"
                + original_name
            )

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    image_filename
                )
            )

        conn = get_db()

        conn.execute(
            """
            INSERT INTO reports
            (
                citizen_username,
                message,
                location,
                image_filename,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["username"],
                message,
                location,
                image_filename,
                "Pending",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("my_reports"))

    return render_template("report.html")


# ---------------- MY REPORTS ----------------

@app.route("/my-reports")
def my_reports():

    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "citizen":
        return redirect(url_for("home"))

    conn = get_db()

    reports = conn.execute(
        """
        SELECT *
        FROM reports
        WHERE citizen_username = ?
        ORDER BY id DESC
        """,
        (session["username"],)
    ).fetchall()

    conn.close()

    return render_template(
        "my_reports.html",
        reports=reports
    )


# ---------------- WORKER REPORTS ----------------

@app.route("/reports")
def reports():

    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "worker":
        return redirect(url_for("home"))

    conn = get_db()

    reports = conn.execute(
        """
        SELECT *
        FROM reports
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        reports=reports
    )


# ---------------- UPDATE REPORT ----------------

@app.route("/update-report/<int:report_id>", methods=["POST"])
def update_report(report_id):

    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "worker":
        return redirect(url_for("home"))

    status = request.form["status"]

    allowed_status = [
        "Pending",
        "In Progress",
        "Resolved"
    ]

    if status not in allowed_status:
        status = "Pending"

    conn = get_db()

    conn.execute(
        """
        UPDATE reports
        SET status = ?
        WHERE id = ?
        """,
        (status, report_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("reports"))


# ---------------- RUN ----------------

if __name__ == "__main__":

    print("Eco Track is starting...")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
