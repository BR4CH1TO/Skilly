"""Aplicación idempotente del índice validado para el listado de profesionales."""
from django.core.management.base import BaseCommand
from core.storage import catalog_indexes, database


class Command(BaseCommand):
    help = 'Añade el índice del catálogo sin modificar documentos ni retirar índices.'

    def handle(self, *args, **options):
        name = catalog_indexes(database())
        self.stdout.write(self.style.SUCCESS('Índice disponible: ' + name))
