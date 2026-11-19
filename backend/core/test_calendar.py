import json
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
from django.test import Client


class AvailabilityTests(TestCase):
    def call(self, role='admin', slots=None, version=1, owner='p'):
        self.db=MagicMock()
        self.db.profesionales.find_one.return_value={'_id':'p','_version':1}
        self.db.profesionales.find_one_and_update.return_value={'_id':'p','_version':2}
        with ExitStack() as stack:
            stack.enter_context(patch('core.access.current_user',return_value={'_id':'u','nombre':'Prueba','rol':role,'perfilId':owner}))
            stack.enter_context(patch('core.workflow_views.database',return_value=self.db))
            stack.enter_context(patch('core.workflow_views.review_profile'))
            stack.enter_context(patch('core.workflow_views.audit'))
            return Client(HTTP_HOST='localhost').put('/api/profesionales/p/disponibilidad/',data=json.dumps({'version':version,'horarios':slots or []}),content_type='application/json')

    def test_normalizes_and_deduplicates_future_slots(self):
        slot=(datetime.now(timezone.utc)+timedelta(days=3)).replace(microsecond=0)
        response=self.call(slots=[slot.isoformat(),slot.isoformat().replace('+00:00','Z')])
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()['horarios']),1)
        self.db.profesionales.find_one_and_update.assert_called_once()

    def test_past_slots_do_not_write(self):
        response=self.call(slots=[(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()])
        self.assertEqual(response.status_code,400)
        self.db.profesionales.find_one_and_update.assert_not_called()

    def test_foreign_professional_and_company_cannot_write(self):
        for role in ['profesional','empresa']:
            self.assertEqual(self.call(role=role,owner='other').status_code,403)
            self.db.profesionales.find_one_and_update.assert_not_called()

    def test_stale_version_does_not_write(self):
        self.assertEqual(self.call(version=0).status_code,400)
        self.db.profesionales.find_one_and_update.assert_not_called()
