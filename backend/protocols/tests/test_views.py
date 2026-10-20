from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from api.models import UserPageAccess
from protocols.models import TemplateLink, TemplateMaterial
from protocols.tests.factories import link, material, plan_row, row_material, task, template

TASK = 'protocols.views.moysklad.task'


class ProtocolsApiTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('arseniy', password='secret')
        self.client = Client()
        self.client.login(username='arseniy', password='secret')
        self.access = UserPageAccess.objects.create(user=user, page_key='protocols')
        self.calcium = material('Мультикальций', 'm-mc')
        self.template = template('Мультикальций', rows=['Мультикальций'])
        row_material(self.template, 'Мультикальций', self.calcium)
        link('p-1', self.template)
        self.task = task(plan_row('p-1', [('МультиКальций 1000 г', 10)], [('m-mc', 'Мультикальций', 9500)]))

    def test_closed_without_page_access(self):
        self.access.delete()
        self.assertEqual(self.client.get('/api/protocols/tasks/').status_code, 403)

    def test_task_shows_prepared_protocol(self):
        with patch(TASK, return_value=self.task):
            payload = self.client.get('/api/protocols/tasks/t-1/').json()
        self.assertEqual(payload['variants'][0]['template']['title'], 'Мультикальций')
        self.assertEqual(payload['variants'][0]['rows'][0]['qty'], 9500)

    def test_docx_download(self):
        rows = [{'row_name': 'Мультикальций', 'material_id': 'm-mc', 'qty': 9500, 'series': '379'}]
        with patch(TASK, return_value=self.task):
            response = self.client.post('/api/protocols/tasks/t-1/docx/', {'variant': 0, 'rows': rows}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'PK'))
        self.assertIn('filename*=UTF-8', response['Content-Disposition'])

    def test_chosen_template_is_remembered_for_the_plan(self):
        other = template('Другой')
        self.client.post('/api/protocols/template-links/', {'template_id': other.id, 'plans': [{'id': 'p-1', 'name': 'План'}]}, content_type='application/json')
        self.assertEqual(TemplateLink.objects.get(plan_external_id='p-1').template, other)

    def test_template_row_gets_its_material(self):
        flavor = material('Ароматизатор', 'm-fl')
        self.client.post('/api/protocols/template-materials/', {'template_id': self.template.id, 'row_name': 'Ароматизатор', 'material_id': 'm-fl'}, content_type='application/json')
        self.assertEqual(TemplateMaterial.objects.get(row_name='Ароматизатор').material, flavor)

    def test_bad_input_gets_a_clear_400(self):
        with patch(TASK, return_value=self.task):
            wrong_index = self.client.post('/api/protocols/tasks/t-1/docx/', {'variant': 5, 'rows': []}, content_type='application/json')
            wrong_qty = self.client.post('/api/protocols/tasks/t-1/docx/', {'variant': 0, 'rows': [{'row_name': 'Мультикальций', 'qty': '1.2.3'}]}, content_type='application/json')
        empty_template = self.client.post('/api/protocols/template-links/', {'template_id': '', 'plans': [{'id': 'p-1', 'name': 'План'}]}, content_type='application/json')
        self.assertEqual([wrong_index.status_code, wrong_qty.status_code, empty_template.status_code], [400, 400, 400])
        self.assertEqual(wrong_qty.json()['error'], 'Количество «1.2.3» не число')
