"""Production WSGI entry point."""

from backend.app import app
from backend.config import Config
from waitress import serve


if __name__ == "__main__":
    serve(app, host=Config.HOST, port=Config.PORT, threads=12)
