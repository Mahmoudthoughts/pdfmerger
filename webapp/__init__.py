from flask import Flask, render_template


def create_app() -> Flask:
    """Application factory for the PDF merger web interface."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    @app.route("/")
    def upload():
        """Render the upload interface."""
        return render_template("upload.html")

    return app
