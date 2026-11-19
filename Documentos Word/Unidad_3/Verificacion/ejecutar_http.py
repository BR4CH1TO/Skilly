"""Ejecuta el laboratorio HTTP en localhost y retira únicamente su base temporal."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--salida',type=Path,required=True,help='Directorio nuevo de evidencias; no se sobrescriben resultados existentes.')
    args=parser.parse_args()
    if args.salida.exists():raise SystemExit('Selecciona un directorio de salida que aún no exista.')
    project=next((p for p in Path(__file__).resolve().parents if (p/'backend/manage.py').is_file()),None)
    if project is None:raise SystemExit('No se encontró backend/manage.py; conserva este script dentro del proyecto.')
    sys.path.insert(0,str(project/'backend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');os.environ['SKILLY_INTEGRATION']='1'
    import django
    django.setup()
    from django.conf import settings
    if urlparse(settings.DATABASES['default']['HOST']).hostname not in ('localhost','127.0.0.1','::1'):
        raise SystemExit('Este laboratorio solo admite MongoDB local. No apunta a servidores remotos.')
    from core.test_integration import RealIntegrationTests
    args.salida.mkdir(parents=True);(args.salida/'evidence').mkdir()
    case=RealIntegrationTests();server=None;log=None
    case.setUp()
    try:
        case.test_complete_flow_permissions_and_recovery()
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        info={'database':case.name,'documents':case.files,'password':case.password,'admin':'admin@example.com','company':'company@example.com','professional':'pro@example.com'}
        secret=args.salida/'fixture-secret.json';secret.write_text(json.dumps(info));secret.chmod(0o600)
        env=dict(os.environ,MONGODB_DB_NAME=case.name,SKILLY_DOCUMENT_ROOT=case.files,DJANGO_DEBUG='true',SKILLY_EVIDENCE_ROOT=str(args.salida.resolve()),SKILLY_HTTP_BASE='http://127.0.0.1:'+str(port))
        log=(args.salida/'evidence/http_server.log').open('w')
        server=subprocess.Popen([sys.executable,'backend/manage.py','runserver','127.0.0.1:'+str(port),'--noreload'],cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
        import requests
        for _ in range(40):
            if server.poll() is not None:raise RuntimeError('El servidor terminó antes de iniciar.')
            try:
                if requests.get(env['SKILLY_HTTP_BASE']+'/api/auth/sesion/',timeout=1).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.25)
        else:raise RuntimeError('No inició el servidor HTTP.')
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('casos_unidad3.py'))],cwd=project,env=env)
        if result.returncode:raise RuntimeError('Las pruebas no terminaron correctamente; conserva la salida de error.')
        print('Evidencias generadas en',args.salida)
    finally:
        if server:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        if log:log.close()
        (args.salida/'fixture-secret.json').unlink(missing_ok=True)
        case.cleanup()


if __name__=='__main__':main()
