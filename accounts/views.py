from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.cache import cache

LOCK_LIMIT = 8
LOCK_SECONDS = 15 * 60


class RateLimitedLoginView(LoginView):
    template_name = "registration/login.html"

    def _cache_key(self):
        forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (forwarded.split(",")[0] if forwarded else self.request.META.get("REMOTE_ADDR", "")).strip()
        return f"login-throttle:{ip or 'unknown'}"

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and cache.get(self._cache_key(), 0) >= LOCK_LIMIT:
            messages.error(request, "تجاوزت عدد محاولات الدخول. حاول بعد ربع ساعة.")
            return self.get(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._cache_key()
        cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._cache_key())
        return super().form_valid(form)
