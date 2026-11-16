"""
Start-up file for PythonAnywhere (pythonanywhere.com), where Velox Health runs online.

On PythonAnywhere: Web tab > "WSGI configuration file" > replace everything in it with this file.
It assumes the app was unzipped to /home/<your username>/velox-health.
"""

import os
import sys

APP_DIR = os.path.join(os.path.expanduser("~"), "velox-health")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# The online demo: demo data only, Apple Health uploads switched off (it's a shared server).
os.environ["PUBLIC_DEMO"] = "1"

from app import app as application  # noqa: E402  (PythonAnywhere looks for "application")
