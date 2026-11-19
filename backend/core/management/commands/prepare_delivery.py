import os
from pathlib import Path
from datetime import datetime, timezone
from bson import BSON
from django.conf import settings
from django.core.management.base import BaseCommand
from core.storage import database, ensure_indexes
from core.access import setup_access
from core.workflow import review_profile, review_service
from core.business import projection, expire_requests


class Command(BaseCommand):
    help = "Respalda la base y adapta los registros existentes al recorrido entregable."
    def handle(self, *args, **options):
        db=database()
        root=Path(settings.BASE_DIR)/'private_backups';root.mkdir(parents=True,exist_ok=True)
        path=root/('before-delivery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.bson')
        with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as output:
            for name in db.list_collection_names():
                output.write(BSON.encode({'type':'indexes','collection':name,'indexes':list(db[name].list_indexes())}))
                for record in db[name].find():output.write(BSON.encode({'type':'document','collection':name,'document':record}))
        self.stdout.write('Copia privada: '+str(path))
        ensure_indexes(db);setup_access(db)
        for agenda in db.agendas.find():
            if 'precioAcordado' not in agenda:
                payment=db.pagos.find_one({'agendaId':agenda['_id']})
                service=db.servicios.find_one({'_id':agenda['servicioId']})
                price=payment['monto'] if payment else service['precio']
                state=payment['estado'] if payment else ('pendiente' if agenda['estado']=='realizado' else 'finalizado' if agenda['estado']=='finalizado' else 'espera')
                changes={'precioAcordado':price,'pagoEstado':state,'simulado':True,'_syncPendiente':True}
                if payment and payment.get('evaluacion'):changes['evaluacion']=payment['evaluacion']
                if payment and payment.get('documento'):changes['documento']=payment['documento']
                db.agendas.update_one({'_id':agenda['_id'],'_version':agenda['_version']},{'$set':changes,'$inc':{'_version':1}})
            projection(db,db.agendas.find_one({'_id':agenda['_id']}))
        expire_requests(db)
        for profile in db.profesionales.find({}, {'_id':1}):review_profile(db,profile['_id'])
        for service in db.servicios.find({}, {'_id':1}):review_service(db,service['_id'])
        self.stdout.write(self.style.SUCCESS('Datos conservados, índices preparados y revisiones sincronizadas.'))
