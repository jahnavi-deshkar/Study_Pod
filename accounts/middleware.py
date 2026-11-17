from django.conf import settings
from django.shortcuts import redirect


class StaffPortalIsolationMiddleware:
    """Keep Django staff accounts out of the student/teacher/parent portal."""

    admin_prefix = "/admin/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and (user.is_staff or user.is_superuser):
            path = request.path_info
            is_admin_request = path == "/admin" or path.startswith(self.admin_prefix)
            is_static_request = any(
                prefix and path.startswith(prefix)
                for prefix in (settings.STATIC_URL, settings.MEDIA_URL)
            )
            if not is_admin_request and not is_static_request:
                return redirect(self.admin_prefix)

        return self.get_response(request)
