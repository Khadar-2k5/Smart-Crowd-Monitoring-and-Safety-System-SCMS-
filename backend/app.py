"""Flask application factory for Smart Crowd Monitoring & Safety System."""

from __future__ import annotations

import atexit
from pathlib import Path

from flask import Flask, jsonify, request

from backend.camera_manager import stop_all_managers
from backend.config import Config
from backend.routes.api_routes import api_bp
from backend.routes.analytics_routes import analytics_bp
from backend.routes.camera_routes import camera_bp
from backend.routes.main_routes import main_bp
from backend.routes.monitoring_routes import monitoring_bp
from backend.routes.report_routes import report_bp
from backend.utils.logger import logger
from backend.session_manager import cleanup_expired_sessions, current_session_id


def create_app(config_object=Config) -> Flask:
    config_object.create_directories()
    frontend_root = Path(config_object.PROJECT_ROOT) / "frontend"
    app = Flask(
        __name__,
        template_folder=str(frontend_root / "templates"),
        static_folder=str(frontend_root / "static"),
    )
    app.config.from_object(config_object)

    @app.before_request
    def establish_session():
        identifier = current_session_id()
        cleanup_expired_sessions({identifier})

    app.register_blueprint(main_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(camera_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(analytics_bp)

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="Endpoint not found."), 404
        return ("Page not found.", 404)

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify(success=False, message="Upload exceeds the configured maximum file size."), 413

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled request error: %s", error)
        return jsonify(success=False, message="An unexpected server error occurred."), 500

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        logger.exception("Unhandled application exception")
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="The server could not complete this request. Review the application logs."), 500
        return ("The application encountered an unexpected error. Please refresh and try again.", 500)

    logger.info("Smart Crowd Monitoring application initialized at %s", Path(config_object.PROJECT_ROOT))
    return app


app = create_app()
atexit.register(stop_all_managers)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
