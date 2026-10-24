from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.notifications import push


@api_view(['GET'])
def push_key(request):
    return Response({'publicKey': settings.VAPID_PUBLIC_KEY})


@api_view(['POST'])
def push_subscribe(request):
    endpoint = request.data.get('endpoint') or ''
    keys = request.data.get('keys') or {}
    p256dh, auth = str(keys.get('p256dh') or ''), str(keys.get('auth') or '')
    if not p256dh or not auth or len(endpoint) > 1000 or len(p256dh) > 200 or len(auth) > 100:
        return Response({'error': 'Неполная подписка'}, status=400)
    if not push.is_push_endpoint(endpoint):
        return Response({'error': 'Неизвестный сервис пушей'}, status=400)
    push.subscribe(request.user, endpoint, p256dh, auth, request.META.get('HTTP_USER_AGENT', ''))
    return Response({'subscribed': True})


@api_view(['POST'])
def push_test(request):
    sent, devices = push.send_test(request.user)
    return Response({'sent': sent, 'devices': devices})


@api_view(['POST'])
def push_unsubscribe(request):
    push.unsubscribe(request.user, request.data.get('endpoint') or '')
    return Response({'subscribed': False})
