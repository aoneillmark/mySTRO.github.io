import click
from flask import Flask, render_template, request
import requests
from database import db as database # SQLAlchemy database instance
from models.musicpiece import MusicPiece
import os
from dotenv import load_dotenv
import google.generativeai as genai # Google Generative AI module for recommendations 
import Blueprint as blueprints # Custom blueprints for modular routing
from cli import create_all, drop_all, populate # Custom CLI commands

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(
    __name__,
    template_folder="src/templates",
    static_folder="src/static"
)

# Database initialization and configuration ------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mystro.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["WEATHER_API_KEY"] = os.getenv("WEATHER_API_KEY")
app.config["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=app.config["GOOGLE_API_KEY"])

# Initialize database with Flask app
database.init_app(app)

# Register custom blueprints for additional routes
app.register_blueprint(blueprints.library)

with app.app_context():
    app.cli.add_command(create_all)
    app.cli.add_command(drop_all)
    app.cli.add_command(populate)
    click.echo("CLI commands registered")


# Define application routes ------------------------------------------------

# Library route: Displays all music pieces in the library
@app.route("/library")
def library():
    pieces = MusicPiece.query.all()
    return render_template("library.html", pieces=pieces)

# Form route: Displays a form for user input (GET) or processes submissions (POST)
@app.route("/form", methods=["GET", "POST"])
def home():
    composers_url = "https://api.openopus.org/composer/list/name/all.json"
    response = requests.get(composers_url)

    composers = [] # Default to an empty list if API call fails

    if response.status_code == 200:
        composers_data = response.json() # Parse JSON response
        composers = composers_data.get("composers", []) # Fetch composer data
    else:
        return (
            f"Failed to fetch composers. Status Code: {response.status_code}"
        )

    # List of music genres for user selection
    genres = [
        "Keyboard", "Orchestral", "Chamber",
        "Stage", "Choral", "Opera", "Vocal"
    ]
    return render_template("form.html", composers=composers, genres=genres)

# About route: Displays an "About" page
@app.route("/")
def hello_world():
    return render_template("about.html")

# Weather and mood-based recommendation route
@app.route("/form")
def form():
    return render_template("form.html")


@app.route("/weather-mood")
def weather_mood():
    # Weather API URL with dynamic query for location (London in this case)
    weather_url = (
        f"http://api.weatherapi.com/v1/current.json?"
        f"key={app.config['WEATHER_API_KEY']}&q=London&aqi=no"
    )

    try:
        # Fetch current weather data
        weather_response = requests.get(weather_url)
        weather_data = (
            weather_response.json()
            if weather_response.status_code == 200
            else None
        )

        if weather_data:
            # Fetch popular composers from Open Opus API
            composers_url = (
                "https://api.openopus.org/composer/list/pop.json"
            )
            composers_response = requests.get(composers_url)
            composers = []

            if composers_response.status_code == 200:
                response_data = composers_response.json()
                composers_list = response_data.get(
                    "composers",
                    []
                )
                composers = composers_list[:5]

            # Get weather details step by step
            weather_current = (
                weather_data.get("current", {})
            )
            weather_condition = (
                weather_current.get("condition", {})
            )
            weather_desc = weather_condition.get("text", "")
            temp = weather_current.get("temp_c", 0)

            # Prepare composer names for prompt
            composer_names = []
            for composer in composers:
                name = composer.get("complete_name")
                composer_names.append(name)

            # Configure and prompt Google Generative AI for suggestions
            model = genai.GenerativeModel("gemini-pro")

            # Build prompt in parts
            weather_part = f"Given that it's {weather_desc} and {temp}°C"
            location_part = "in London today,"
            request_part = (
                "suggest a classical music piece that would complement "
                "this weather."
            )
            composer_part = (
                "Consider selecting from works by these composers: "
                f"{', '.join(composer_names)}."
            )
            instruction_part = (
                "Explain briefly why this piece fits the current weather "
                "and mood."
            )
            ending_part = "Keep your response concise but engaging."

            # Combine prompt parts
            prompt = (
                f"{weather_part} {location_part} {request_part} "
                f"{composer_part} {instruction_part} {ending_part}"
            )

            response = model.generate_content(prompt)
            suggestion = response.text
        else:
            suggestion = None

    except Exception as e:
        print(f"Error: {e}") # Log any errors for debugging
        weather_data = None
        suggestion = None

    # Render the weather-mood template with the weather data and suggestion
    return render_template(
        "weather_mood.html",
        weather=weather_data,
        suggestion=suggestion
    )

# Search route: Processes form submissions to search for works
@app.route("/search", methods=["POST"])
def search():
    selected_composer_ids = request.form.getlist("composer_id")
    name = request.form.get("name")
    selected_genres = request.form.getlist("genres")

    if not selected_composer_ids:
        return "No composer selected. Please try again."
    if not selected_genres:
        return "No genres selected. Please try again."

    all_works = [] # To hold works matching the criteria

    for composer_id in selected_composer_ids:
        # Fetch composer information
        composer_url = (
            "https://api.openopus.org/composer/list/"
            f"ids/{composer_id}.json"
        )
        composer_response = requests.get(composer_url)
        composer_name = "Unknown Composer"

        if composer_response.status_code == 200:
            composer_data = composer_response.json()
            composer_name = composer_data.get("composers", [{}])[0].get(
                "complete_name",
                "Unknown Composer"
            )

        # Fetch works by the composer and filter by genre
        works_url = (
            "https://api.openopus.org/work/list/composer/"
            f"{composer_id}/genre/all.json"
        )
        response = requests.get(works_url)

        if response.status_code == 200:
            data = response.json()
            composer_works = data.get("works", [])
            filtered_works = [
                {
                    "title": work.get("title", ""),
                    "genre": work.get("genre", ""),
                    "subtitle": work.get("subtitle", ""),
                    "popular": work.get("popular") == "1",
                    "recommended": work.get("recommended") == "1",
                    "composer_name": composer_name,
                    "composer_id": composer_id,
                }
                for work in composer_works
                if work.get("genre") in selected_genres
            ]
            all_works.extend(filtered_works)
        else:
            return render_template("noresults.html")

    # Extract unique composer names for filters
    unique_composers = sorted(
        list(set(work["composer_name"] for work in all_works))
    )

    # Render results page with filtered works and composers
    return render_template(
        "results.html",
        name=name,
        works=all_works,
        composers=unique_composers
    )

# Run the application
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
