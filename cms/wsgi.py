"""
WSGI config for cms project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ["DJANGO_SETTINGS_MODULE"] = (
        "cms.production" if os.environ.get("DJANGO_ENV") == "production" else "cms.settings"
    )

application = get_wsgi_application()
