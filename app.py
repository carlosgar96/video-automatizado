"""Punto de entrada de la aplicación Flask."""

from flask import Flask

app = Flask(__name__)

# Registrar las rutas de la aplicación.
import routes  # noqa: E402  pylint: disable=wrong-import-position


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
