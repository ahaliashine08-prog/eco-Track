from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json

from google import genai
from google.genai import types


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "ecotrack-secret-key"
)

DATABASE = "ecotrack.db"


# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()

    # USERS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'citizen'
        )
    """)

    # Check whether old database has role column
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    column_names = [column["name"] for column in columns]

    if "role" not in column_names:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN role TEXT NOT NULL DEFAULT 'citizen'
        """)

    # REPORTS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_username TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# IMPORTANT:
# This runs when Render/Gunicorn loads app.py
create_database()


# =========================
# BIN INFORMATION
# =========================

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
        "examples": "Diapers, tissues, thermocol and other general waste"
    }
}


# =========================
# WASTE DATA
# =========================

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

    "vegetable peel": {
        "type": "Biodegradable waste",
        "hazard": 5,
        "bin": "Green",
        "guidance": "Put vegetable peels in the green bin."
    },

    "fruit peel": {
        "type": "Biodegradable waste",
        "hazard": 5,
        "bin": "Green",
        "guidance": "Put fruit peels in the green bin."
    },

    "paper": {
        "type": "Recyclable waste",
        "hazard": 5,
        "bin": "Blue",
        "guidance": "Keep paper dry and put it in the blue bin."
    },

    "cardboard": {
        "type": "Recyclable waste",
        "hazard": 5,
        "bin": "Blue",
        "guidance": "Flatten cardboard and put it in the blue bin."
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
        "guidance": "Do not throw batteries into normal waste. Use an authorised battery collection point."
    },

    "paint": {
        "type": "Special waste",
        "hazard": 85,
        "bin": "Yellow",
        "guidance": "Do not pour paint into drains. Follow local hazardous-waste collection instructions."
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
        "guidance": "Place thermocol in the black bin where local rules classify it as general waste."
    }
}


# =========================
# LOGIN CHECKS
# =========================

def logged_in():
    return "username" in session


def is_citizen():
    return session.get("role") == "citizen"


def is_worker():
    return session.get("role") == "worker"


# =========================
# FIRST PAGE
# =========================

@app.route("/")
def index():

    if logged_in():
        return redirect(url_for("home"))

    return render_template("index.html")


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "citizen")

        if not username or not password:
            return "Username and password are required."

        if role not in ["citizen", "worker"]:
            role = "citizen"

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

            return "Username already exists. Please choose another username."

        except Exception as e:

            conn.close()

            print("REGISTER ERROR:", e)

            return "Registration failed."

    return render_template("register.html")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect(url_for("home"))

        return "Invalid username or password."

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# =========================
# DASHBOARD
# =========================

@app.route("/home")
def home():

    if not logged_in():
        return redirect(url_for("login"))

    # SERVICE WORKER
    if is_worker():

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
            "worker.html",
            username=session["username"],
            reports=reports
        )

    # CITIZEN
    return render_template(
        "home.html",
        username=session["username"],
        role=session["role"]
    )


# =========================
# BINS
# =========================

@app.route("/bins")
def bins():

    if not logged_in():
        return redirect(url_for("login"))

    return render_template(
        "bins.html",
        bins=BIN_INFO
    )


# =========================
# TEXT WASTE HELPER
# =========================

@app.route("/helper", methods=["GET", "POST"])
def helper():

    if not logged_in():
        return redirect(url_for("login"))

    result = None

    if request.method == "POST":

        waste = request.form.get(
            "waste",
            ""
        ).strip().lower()

        if waste in WASTE_DATA:

            result = WASTE_DATA[waste]

        else:

            result = {
                "type": "Unknown waste",
                "hazard": "Unknown",
                "bin": "Cannot determine",
                "guidance": "This waste item is not currently in our database."
            }

    return render_template(
        "helper.html",
        result=result
    )


# =========================
# AI IMAGE DETECTION
# =========================

@app.route("/photo", methods=["POST"])
def photo():

    if not logged_in():
        return redirect(url_for("login"))

    uploaded_file = request.files.get("photo")

    if not uploaded_file or uploaded_file.filename == "":
        return "Please select an image."

    try:

        image_bytes = uploaded_file.read()

        if not image_bytes:
            raise Exception("Empty image file.")

        api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception("GEMINI_API_KEY is missing.")

        client = genai.Client(
            api_key=api_key
        )

        prompt = """
Identify the main waste item in this image.

Return ONLY valid JSON.

Use exactly this format:

{
  "waste": "name of waste",
  "type": "waste type",
  "hazard": 0,
  "bin": "Green",
  "guidance": "short disposal guidance"
}

Rules:

hazard must be a number between 0 and 100.

bin MUST be exactly one of:

Green
Blue
Yellow
Black

Green = biodegradable or wet waste.
Blue = dry recyclable waste.
Yellow = special waste requiring careful disposal.
Black = general non-recyclable waste.

If the image is unclear, give the best possible identification.
"""

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=uploaded_file.mimetype
                ),
                prompt
            ]
        )

        text = response.text.strip()

        # Remove markdown code fences if Gemini adds them
        if text.startswith("```json"):
            text = text[7:]

        if text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        result = json.loads(text)

        allowed_bins = [
            "Green",
            "Blue",
            "Yellow",
            "Black"
        ]

        if result.get("bin") not in allowed_bins:
            result["bin"] = "Cannot determine"

        try:

            hazard = int(
                result.get("hazard", 0)
            )

            hazard = max(
                0,
                min(100, hazard)
            )

            result["hazard"] = hazard

        except Exception:

            result["hazard"] = "Unknown"

        result.setdefault(
            "waste",
            "Unknown"
        )

        result.setdefault(
            "type",
            "Unknown"
        )

        result.setdefault(
            "guidance",
            "Please follow local waste-disposal instructions."
        )

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result=result
        )

    except Exception as e:

        print("AI IMAGE ERROR:", e)

        result = {
            "waste": "Could not identify",
            "type": "Unknown",
            "hazard": "Unknown",
            "bin": "Cannot determine",
            "guidance": "AI detection failed. Please try a clear image."
        }

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result=result
        )


# =========================
# CITIZEN REPORT
# =========================

@app.route("/report", methods=["GET", "POST"])
def report():

    if not logged_in():
        return redirect(url_for("login"))

    if not is_citizen():
        return redirect(url_for("home"))

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        if not message:
            return "Please enter a message."

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO reports
                (citizen_username, message, status)
                VALUES (?, ?, ?)
                """,
                (
                    session["username"],
                    message,
                    "Pending"
                )
            )

            conn.commit()

        except Exception as e:

            print("REPORT ERROR:", e)

            conn.close()

            return "Could not submit the report."

        conn.close()

        return redirect(
            url_for("my_reports")
        )

    return render_template(
        "report.html"
    )


# =========================
# MY REPORTS
# =========================

@app.route("/my-reports")
def my_reports():

    if not logged_in():
        return redirect(url_for("login"))

    if not is_citizen():
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


# =========================
# SERVICE WORKER UPDATE
# =========================

@app.route(
    "/update-report/<int:report_id>",
    methods=["POST"]
)
def update_report(report_id):

    if not logged_in():
        return redirect(url_for("login"))

    if not is_worker():
        return redirect(url_for("home"))

    status = request.form.get(
        "status",
        "Pending"
    )

    allowed_status = [
        "Pending",
        "In Progress",
        "Completed"
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

    return redirect(
        url_for("home")
    )


# =========================
# RUN LOCALLY
# =========================

if __name__ == "__main__":

    print("Eco Track is starting...")

    app.run(
        host="0.0.0.0",
        port=5000
    )
