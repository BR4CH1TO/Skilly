"""Regresión de métodos de página y configuración segura del entorno."""
import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase
from django.test import Client


class HardeningTests(TestCase):
    def test_html_routes_reject_mutating_methods(self):
        client=Client(HTTP_HOST='localhost')
        for route in ['/', '/terminos/', '/panel/', '/cuenta/']:
            for method in ['post','put','patch','delete']:
                self.assertEqual(getattr(client,method)(route).status_code,405,(route,method))

    def test_public_html_supports_head_without_body(self):
        client=Client(HTTP_HOST='localhost')
        for route in ['/', '/terminos/']:
            response=client.head(route)
            self.assertEqual(response.status_code,200)
            self.assertEqual(b''.join(response.streaming_content),b'')
            response.close()

    def test_generated_development_key_and_required_production_key(self):
        backend=Path(__file__).resolve().parents[1]
        env=dict(os.environ,DJANGO_DEBUG='true')
        env.pop('DJANGO_SECRET_KEY',None)
        # Evita que un .env local suministre una clave y oculte la comprobación del respaldo.
        code=('from unittest.mock import patch; '
              'from importlib import import_module; '
              'import hashlib; '
              'p=patch("dotenv.load_dotenv");p.start(); '
              's=import_module("config.settings"); '
              'print(hashlib.sha256(s.SECRET_KEY.encode()).hexdigest())')
        first=subprocess.run([sys.executable,'-c',code],cwd=backend,env=env,capture_output=True,text=True,check=True)
        second=subprocess.run([sys.executable,'-c',code],cwd=backend,env=env,capture_output=True,text=True,check=True)
        self.assertNotEqual(first.stdout.strip(),second.stdout.strip())
        env['DJANGO_DEBUG']='false'
        production=subprocess.run([sys.executable,'-c',code],cwd=backend,env=env,capture_output=True,text=True)
        self.assertNotEqual(production.returncode,0)
        self.assertIn('DJANGO_SECRET_KEY',production.stderr)
