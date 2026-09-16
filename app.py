from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from google import genai
from google.genai import types
import json

app = Flask(__name__)
app.secret_key = "ecotrack-secret-key"

DATABASE = "ecotrack.db"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ---------------- BIN INFORMATION ----------------

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


# ---------------- WASTE DATA ----------------

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
        "guidance": "Do not flush unused medicine. Use an appropriate medicine take-back or collection facility."
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


# ---------------- HOME PAGE ----------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            conn.close()
            return "Username already exists!"

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session["username"] = username

            return redirect(url_for("home"))

        return "Invalid username or password!"

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.pop("username", None)

    return redirect(url_for("index"))


# ---------------- ECO TRACK HOME ----------------

@app.route("/home")
def home():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template(
        "home.html",
        username=session["username"]
    )


# ---------------- BIN TYPES ----------------

@app.route("/bins")
def bins():

    if "username" not in session:
        return redirect(url_for("login"))

    return render_template(
        "bins.html",
        bins=BIN_INFO
    )


# ---------------- WASTE DISPOSAL HELPER ----------------

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
                "guidance": "This waste item is not in our current database."
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

        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        prompt = """
        Identify the main waste item in this image.

        Return ONLY valid JSON in this format:
        {
          "waste": "name of waste item",
          "hazard": 0,
          "bin": "Green",
          "guidance": "short disposal guidance"
        }

        Use only one of these bins:
        Green, Blue, Yellow, Black.

        Hazard must be a number from 0 to 100.
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
        text = text.replace("```json", "").replace("```", "").strip()

        result = json.loads(text)

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result=result
        )

    except Exception as e:

        return render_template(
            "photo_result.html",
            filename=uploaded_file.filename,
            result={
                "waste": "Could not identify",
                "hazard": "Unknown",
                "bin": "Cannot determine",
                "guidance": "Image detection failed. Please try another clear photo."
            }
        )
# ---------------- START APP ----------------

if __name__ == "__main__":

    create_database()

    print("Eco Track is starting...")
    print("Open this address in your browser:")
    print("http://127.0.0.1:5000")

    app.run(host="0.0.0.0", port=5000)
