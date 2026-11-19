from io import BytesIO
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def inspect_pdf(content):
    if not 20 <= len(content) <= 5 * 1024 * 1024:
        raise ValueError("El PDF debe tener un tamaño máximo de 5 MiB.")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("El documento no puede estar protegido con contraseña.")
        if not 1 <= len(reader.pages) <= 100:
            raise ValueError("El documento debe contener entre 1 y 100 páginas.")
        root = reader.trailer['/Root']
        names = root.get('/Names', {})
        if hasattr(names, 'get_object'):
            names = names.get_object()
        if root.get('/OpenAction') or root.get('/AA') or names.get('/JavaScript') or names.get('/EmbeddedFiles'):
            raise ValueError("No se permiten PDF con acciones automáticas o archivos adjuntos.")
        for page in reader.pages:
            if page.get('/AA'):
                raise ValueError("El PDF contiene acciones no permitidas.")
            for ref in page.get('/Annots', []):
                annotation = ref.get_object()
                action = annotation.get('/A')
                if action and action.get_object().get('/S') in ('/JavaScript', '/Launch', '/SubmitForm', '/GoToR'):
                    raise ValueError("El PDF contiene acciones no permitidas.")
        return {"paginas": len(reader.pages), "metodo": "Estructura PDF verificada con pypdf", "contenidoVerificado": False}
    except ValueError:
        raise
    except (PdfReadError, KeyError, TypeError, AttributeError, IndexError, RecursionError, EOFError):
        raise ValueError("El archivo no tiene una estructura PDF válida o está dañado.") from None
