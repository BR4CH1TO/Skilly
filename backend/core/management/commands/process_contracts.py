from django.core.management.base import BaseCommand
from core.storage import database, contract_indexes
from core.contract_views import reconcile
from core.contracts import monitor


class Command(BaseCommand):
    help='Reconcilia acuerdos y genera recordatorios internos, sin mover dinero real.'
    def handle(self,*args,**options):
        db=database();contract_indexes(db);reconcile(db)
        from core.account_controls import project_restrictions
        project_restrictions(db)
        self.stdout.write(f'Acuerdos con nuevos avisos: {monitor(db)}. No se ejecutaron cobros reales.')
