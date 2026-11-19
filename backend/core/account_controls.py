from datetime import datetime, timezone


def restricted(user):
    r=user.get('restriccionComercial')
    if not r: return False
    return datetime.fromisoformat(r['desde'].replace('Z','+00:00'))<=datetime.now(timezone.utc)


def require_commercial(user):
    if restricted(user): raise ValueError('Tu cuenta tiene una restricción comercial. Puedes consultar tus acuerdos y pedir revisión desde Privacidad y atención.')


def project_restrictions(db):
    for user in db.usuarios.find({'rol':{'$in':['empresa','profesional']}}):
        target='profesionales' if user['rol']=='profesional' else 'empresas'
        db[target].update_one({'_id':user['perfilId']},{'$set':{'restriccionComercialActiva':restricted(user)}})
