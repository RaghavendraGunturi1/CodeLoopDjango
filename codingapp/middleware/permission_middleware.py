from django.shortcuts import redirect
from django.contrib import messages

class RoleAccessMiddleware:
    """
    Example: block users from visiting admin-only routes unless they have Admin role.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lower()

        if "permissions/manage" in path and request.user.is_authenticated:
            profile = getattr(request.user, "userprofile", None)
            if not profile or profile.role.name.lower() != "admin":
                messages.error(request, "You don’t have permission to access that page.")
                return redirect("dashboard")

        if "permissions/hod" in path and request.user.is_authenticated:
            profile = getattr(request.user, "userprofile", None)
            if not profile or profile.role.name.lower() != "hod":
                messages.error(request, "Only HODs can access that page.")
                return redirect("dashboard")

        return self.get_response(request)
