"""
ASGI config for cms project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ["DJANGO_SETTINGS_MODULE"] = (
        "cms.production" if os.environ.get("DJANGO_ENV") == "production" else "cms.settings"
    )

application = get_asgi_application()
