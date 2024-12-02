from flask import Blueprint, render_template, redirect, url_for, request
from database import db
from models.musicpiece import MusicPiece
from models.user import User
from models.userlibrary import UserLibrary

# Define the Blueprint for the library
library = Blueprint("library", __name__, url_prefix="/library")


@library.route("/", methods=["GET"])
def all_pieces():
    user_name = request.args.get("user_name")
    if not user_name:
        return render_template("library.html", pieces=[], username_missing=True)

    user = User.query.filter_by(username=user_name).first()
    if not user:
        return render_template("library.html", pieces=[], username_missing=False, user_name=user_name)

    user_pieces = [entry.music_piece for entry in user.library]
    return render_template("library.html", pieces=user_pieces, username_missing=False, user_name=user_name)




@library.route("/add_piece", methods=["GET", "POST"])
def add_piece():
    """
    Add a new music piece to the library.
    """
    user_name = request.form.get("user_name")
    composer = request.form.get("composer_name")
    title = request.form.get("title")
    subtitle = request.form.get("subtitle")
    genre = request.form.get("genre")
    popular = request.form.get("popular") == "true"
    recommended = request.form.get("recommended") == "true"

    user = User.query.filter_by(username=user_name).first()
    if not user:
        user = User(username=user_name)
        db.session.add(user)
        db.session.commit()

    music_piece = MusicPiece.query.filter_by(composer=composer, title=title, subtitle=subtitle).first()
    if not music_piece:
        music_piece = MusicPiece(
            composer=composer,
            title=title,
            subtitle=subtitle,
            genre=genre,
            popular=popular,
            recommended=recommended,
        )
        db.session.add(music_piece)
        db.session.commit()

    # Link user to music piece
    user_library_entry = UserLibrary(user_id=user.id, music_piece_id=music_piece.id)
    db.session.add(user_library_entry)
    db.session.commit()

    return redirect(url_for("library.all_pieces", user_name=user_name))


@library.route("/<int:piece_id>", methods=["GET", "POST"])
def single_piece(piece_id):
    """
    View or delete a single music piece.
    """
    music_piece = db.get_or_404(
        MusicPiece, piece_id, description="Music piece not found."
    )

    if request.method == "POST":
        # Handle delete action
        if request.form.get("submit_button") == "delete":
            db.session.delete(music_piece)
            db.session.commit()
            return redirect(url_for("library.all_pieces"))

    return render_template("library_piece.html", piece=music_piece)


@library.route("/form", methods=["GET", "POST"])
def library_form():
    """
    Display and handle the library form.
    User can search for music pieces based on selected criteria.
    """
    try:
        response = request.get("https://api.openopus.org/composer/list/name/all.json")
        composers = response.json()["composers"] if response.status_code == 200 else []
    except Exception:
        composers = []

    genres = [
        "Keyboard",
        "Orchestral",
        "Chamber",
        "Stage",
        "Choral",
        "Opera",
        "Vocal",
    ]

    return render_template("form.html", composers=composers, genres=genres)
