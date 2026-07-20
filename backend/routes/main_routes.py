"""Server-rendered application pages."""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
@main_bp.get("/home")
def home():
    return render_template("index.html", initial_page="home")


@main_bp.get("/monitoring")
def monitoring():
    return render_template("index.html", initial_page="monitoring")


@main_bp.get("/reports")
def reports():
    return render_template("index.html", initial_page="reports")


@main_bp.get("/analytics")
def analytics():
    return render_template("index.html", initial_page="analytics")


@main_bp.get("/logs")
def logs():
    return render_template("index.html", initial_page="logs")


@main_bp.get("/settings")
def settings():
    return render_template("index.html", initial_page="settings")


@main_bp.get("/about")
def about():
    return render_template("index.html", initial_page="about")

@main_bp.get("/help")
def help():
    return render_template("index.html", initial_page="help")