from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from api.auth import login_required_api
from api.services.home import home_payload


@login_required_api
@require_http_methods(['GET'])
def home_view(request):
    return JsonResponse({'status': 'success', 'data': home_payload(request.user)})
