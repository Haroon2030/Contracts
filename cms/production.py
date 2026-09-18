import os

os.environ.setdefault("DJANGO_ENV", "production")
os.environ.setdefault("DJANGO_DEBUG", "0")

from .settings import *  # noqa: E402,F401,F403

if DEBUG:
    raise RuntimeError("cms.production refuses DEBUG=True.")
