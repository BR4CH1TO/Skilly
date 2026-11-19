from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch
from django.test import Client, override_settings
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from .pdf_validation import inspect_pdf
from .business import instant, transition, book
from .storage import validate_record


def pdf_bytes(encrypted=False, javascript=False):
    writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 700 Td (Documento de prueba) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    if encrypted:writer.encrypt('private')
    if javascript:writer.add_js('app.alert("test")')
    out=BytesIO();writer.write(out);return out.getvalue()


class DeliveryTests(TestCase):
    def test_forged_pdf_rejected(self):
        with self.assertRaises(ValueError):inspect_pdf(b'%PDF-fake\narbitrary content\n%%EOF')
    def test_structural_pdf_accepted_without_authenticity_claim(self):
        result=inspect_pdf(pdf_bytes());self.assertEqual(result['paginas'],1);self.assertFalse(result['contenidoVerificado'])
    def test_encrypted_pdf_rejected(self):
        with self.assertRaises(ValueError):inspect_pdf(pdf_bytes(encrypted=True))
    def test_active_pdf_rejected(self):
        with self.assertRaises(ValueError):inspect_pdf(pdf_bytes(javascript=True))
    def test_dates_normalized_for_slot_comparison(self):
        self.assertEqual(instant('2026-09-29T09:00:00-03:00'),instant('2026-09-29T12:00:00Z'))
    def test_invalid_optional_type_rejected(self):
        with self.assertRaises(ValueError):validate_record('profesionales',{'id':'p','nombre':'Prueba','profesion':'Diseño','estado':'revision','habilidades':'invalid'},MagicMock())
    def test_payment_cannot_skip_realization(self):
        db=MagicMock();db.agendas.find_one.return_value={'_id':'a','_version':1,'estado':'confirmado','pagoEstado':'espera','empresaId':'c'}
        with self.assertRaises(ValueError):transition(db,{'_id':'u','nombre':'Empresa','rol':'empresa','perfilId':'c'},'a',1,'pagar')
        db.agendas.find_one_and_update.assert_not_called()
    def test_user_cannot_operate_foreign_agenda(self):
        db=MagicMock();db.agendas.find_one.return_value={'_id':'a','_version':1,'estado':'propuesto','empresaId':'other'}
        with self.assertRaises(ValueError):transition(db,{'_id':'u','nombre':'Empresa','rol':'empresa','perfilId':'c'},'a',1,'cancelar')
    def test_same_booking_key_replays_existing_record(self):
        db=MagicMock();existing={'_id':'a','solicitudId':'r','fecha':datetime(2026,11,1,tzinfo=timezone.utc)}
        db.agendas.find_one.return_value=existing
        with patch('core.business.projection'):
            self.assertEqual(book(db,{'_id':'u','rol':'empresa'},'r','2026-11-01T00:00:00Z','operation-123'),existing)
        db.agendas.insert_one.assert_not_called()
    def test_direct_payment_edits_are_denied_even_to_admin(self):
        with patch('core.access.current_user',return_value={'_id':'a','rol':'admin'}),patch('core.views.database'):
            result=Client(HTTP_HOST='localhost').put('/api/pagos/p/',data='{}',content_type='application/json')
            self.assertEqual(result.status_code,403)
    def test_static_files_available_with_debug_false(self):
        with TemporaryDirectory() as temp:
            path=Path(temp)/'css';path.mkdir();(path/'test.css').write_text('body{color:black}')
            with override_settings(DEBUG=False,SECURE_SSL_REDIRECT=False,STATIC_ROOT=temp):
                response=Client(HTTP_HOST='localhost').get('/static/css/test.css')
                self.assertEqual(response.status_code,200);response.close()
