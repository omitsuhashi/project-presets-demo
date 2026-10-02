import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Local demo only. Deployment supplies its own secret and settings.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-demo-only")
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INSTALLED_APPS = []
MIDDLEWARE = []
ROOT_URLCONF = "demo.urls"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
USE_TZ = True
