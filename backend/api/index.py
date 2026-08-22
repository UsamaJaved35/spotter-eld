"""Vercel serverless entrypoint.

Vercel routes every request to this module and calls the WSGI callable it
exports. Django's own URLconf takes it from there, so routing is unchanged
between local `runserver` and production.

The explicit `api/` file-based convention is used rather than relying on
framework auto-detection, which did not engage for this project.
"""

import os
import sys
from pathlib import Path

# Vercel executes with the project root as the working directory, but the
# bundle's import path does not always include it. Add it so `config` and
# `trips` resolve.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402

# Vercel's Python runtime looks for `app` (most WSGI/ASGI frameworks) or
# `application` (Django). Both are exported so either lookup succeeds.
app = application
