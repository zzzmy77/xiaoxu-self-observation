"""Entrypoint for production — reads PORT from env and starts waitress."""
import os
from waitress import serve
from app import application

port = int(os.environ.get("PORT", 8080))
serve(application, port=port)
