from urllib.parse import quote

from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.models import RawMaterial
from protocols.models import ProtocolTemplate, TemplateLink, TemplateMaterial
from protocols.services import moysklad
from protocols.services.assemble import prepare
from protocols.services.protocol_file import ProtocolError, build

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@api_view(['GET'])
def task_list(request):
    return Response({'tasks': moysklad.recent_tasks(request.GET.get('search', '').strip())})


@api_view(['GET'])
def task_detail(request, task_id):
    task = moysklad.task(task_id)
    return Response({
        'task': {'id': task['id'], 'name': task['name'], 'moment': task['moment']},
        'variants': prepare(task),
        'templates': list(ProtocolTemplate.objects.values('id', 'title')),
    })


@api_view(['POST'])
def task_docx(request, task_id):
    task = moysklad.task(task_id)
    try:
        content, filename = build(task, request.data.get('variant'), request.data.get('rows') or [])
    except ProtocolError as error:
        return Response({'error': str(error)}, status=400)
    response = HttpResponse(content, content_type=DOCX)
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


def _bad(message):
    return Response({'error': message}, status=400)


@api_view(['POST'])
def link_template(request):
    template = ProtocolTemplate.objects.filter(id=request.data.get('template_id') or 0).first()
    plans = request.data.get('plans') or []
    if template is None or not plans:
        return _bad('Выберите шаблон')
    for plan in plans:
        TemplateLink.objects.update_or_create(
            plan_external_id=plan['id'], defaults={'plan_name': plan['name'], 'template': template},
        )
    return Response({'ok': True})


@api_view(['POST'])
def link_material(request):
    template = ProtocolTemplate.objects.filter(id=request.data.get('template_id') or 0).first()
    material = RawMaterial.objects.filter(external_id=request.data.get('material_id') or '').first()
    if template is None or material is None or not request.data.get('row_name'):
        return _bad('Выберите сырьё для строки шаблона')
    TemplateMaterial.objects.update_or_create(
        template=template, row_name=request.data['row_name'], defaults={'material': material},
    )
    return Response({'ok': True})
