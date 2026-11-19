"""Importa la demostración completa en una base nueva; nunca sobrescribe datos."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone


def load_package(root):
    from bson import json_util
    inventory = json_util.loads((root / 'Inventario.json').read_text(encoding='utf-8'))
    records = {}
    for name, spec in inventory['colecciones'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
            raise ValueError('Nombre de colección inválido.')
        path = root / 'Colecciones' / (name + '.json')
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError('El archivo de colección fue alterado: ' + name)
        records[name] = json_util.loads(path.read_text(encoding='utf-8'))
        if len(records[name]) != spec['documentos']:
            raise ValueError('Conteo incorrecto: ' + name)
    for name, expected in inventory['archivos_pdf'].items():
        if Path(name).name != name or not name.endswith('.pdf'):
            raise ValueError('Nombre PDF inválido.')
        if hashlib.sha256((root / 'PDF_demostracion' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('El PDF fue alterado: ' + name)
    for name in ['usuarios', 'sesiones', 'intentos', 'atencion']:
        if records.get(name):
            raise ValueError('La copia no debe contener cuentas, sesiones ni atención privadas.')
    return inventory, records


def restore(db, inventory, records, password):
    from django.contrib.auth.hashers import make_password
    if not re.fullmatch(r'skilly_evaluacion(?:_[a-z0-9_]+)?', db.name):
        raise ValueError('Solo se admite skilly_evaluacion o skilly_evaluacion_<sufijo>.')
    if db.list_collection_names():
        raise ValueError('La base destino ya existe con colecciones. No se sobrescribe. Usa otro nombre con --base.')
    professional = next((p for p in records['profesionales'] if p.get('estado') == 'validado'), records['profesionales'][0])
    company = records['empresas'][0]
    for name, spec in inventory['colecciones'].items():
        db.create_collection(name, **spec['options'])
        if records[name]:
            db[name].insert_many(records[name])
        for index in spec['indices']:
            db[name].create_index([tuple(k) for k in index['key']], **index['options'])
    users = [
        {'_id': 'demo-admin', 'nombre': 'Administración de demostración', 'correo': 'admin@skilly.example.invalid', 'rol': 'admin'},
        {'_id': 'demo-empresa', 'nombre': 'Empresa de demostración', 'correo': 'empresa@skilly.example.invalid', 'rol': 'empresa', 'perfilId': company['_id']},
        {'_id': 'demo-profesional', 'nombre': 'Profesional de demostración', 'correo': 'profesional@skilly.example.invalid', 'rol': 'profesional', 'perfilId': professional['_id']},
    ]
    for user in users:
        user.update(activo=True, passwordHash=make_password(password), fecha=datetime.now(timezone.utc))
    db.usuarios.insert_many(users)
    for name, spec in inventory['colecciones'].items():
        expected = spec['documentos'] + (3 if name == 'usuarios' else 0)
        if db[name].count_documents({}) != expected:
            raise ValueError('Verificación fallida: ' + name)
    return users


def configure_project(project, database_name):
    path = project / 'backend' / '.env'
    original = path.read_text(encoding='utf-8-sig') if path.exists() else (project / 'backend' / '.env.example').read_text(encoding='utf-8')
    pattern = r'(?m)^MONGODB_DB_NAME=.*$'
    text = re.sub(pattern, 'MONGODB_DB_NAME=' + database_name, original) if re.search(pattern, original) else original.rstrip() + '\nMONGODB_DB_NAME=' + database_name + '\n'
    path.write_text(text, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Importa colecciones, índices y PDF de demostración de Skilly en una base nueva.')
    parser.add_argument('--base', default='skilly_evaluacion', help='Base nueva: skilly_evaluacion o skilly_evaluacion_<sufijo>.')
    args = parser.parse_args()
    if not re.fullmatch(r'skilly_evaluacion(?:_[a-z0-9_]+)?', args.base):
        parser.error('Nombre no permitido. Ejemplo: --base skilly_evaluacion_segunda')
    package = Path(__file__).resolve().parent
    project = package.parent
    if not (project / 'backend' / 'manage.py').is_file():
        raise SystemExit('Conserva Base_de_datos dentro de la raíz del proyecto.')
    sys.path.insert(0, str(project / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth.password_validation import validate_password
    from pymongo import MongoClient
    inventory, records = load_package(package)
    print('Destino:', args.base, '· No se sobrescribirá ninguna base existente.')
    print('Se crearán tres cuentas locales de demostración con la contraseña que elijas.')
    password = getpass.getpass('Contraseña de demostración (mínimo 8 caracteres): ')
    validate_password(password)
    if password != getpass.getpass('Repite la contraseña: '):
        raise ValueError('Las contraseñas no coinciden.')
    client = MongoClient(settings.DATABASES['default']['HOST'], serverSelectionTimeoutMS=5000)
    created = False
    new_files = []
    try:
        client.admin.command('ping')
        db = client[args.base]
        if db.list_collection_names():
            raise ValueError('La base ya contiene colecciones. Usa --base skilly_evaluacion_segunda; no se reemplazó nada.')
        from django.conf import settings
        private = Path(settings.PRIVATE_DOCUMENT_ROOT)
        for name, expected in inventory['archivos_pdf'].items():
            target = private / name
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('Ya existe un PDF diferente con el mismo nombre. No se sobrescribió: ' + name)
        created = True
        users = restore(db, inventory, records, password)
        private.mkdir(parents=True, exist_ok=True)
        for name in inventory['archivos_pdf']:
            target = private / name
            if not target.exists():
                shutil.copy2(package / 'PDF_demostracion' / name, target)
                new_files.append(target)
        configure_project(project, args.base)
        print('Importación verificada:', len(inventory['colecciones']), 'colecciones; tres cuentas nuevas; PDF de prueba disponibles.')
        for user in users:
            print(user['rol'] + ': ' + user['correo'])
        print('Usa en las tres cuentas la contraseña que acabas de elegir. No se imprime ni se incluye en los archivos.')
        print('La conexión del proyecto quedó configurada en backend/.env para ' + args.base + '.')
        print('Inicia Django: python backend/manage.py runserver')
    except Exception:
        if created:
            client.drop_database(args.base)
            for target in new_files:
                target.unlink(missing_ok=True)
        raise
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('No se completó la importación:', str(error), file=sys.stderr)
        sys.exit(1)
