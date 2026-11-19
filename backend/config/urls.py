from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import FileResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from django.urls import path, re_path
from django.views.static import serve
from core.views import records, state
from core import workflow_views, auth_views, portal_views, business_views
from core.access import current_user
from core import contract_views


def html_file(name):
    return FileResponse((settings.PROJECT_DIR / "pages" / name).open("rb"), content_type="text/html; charset=utf-8")


@require_safe
def index(request):
    return html_file("public.html")


@never_cache
@require_safe
def panel(request):
    user = current_user(request)
    if user is None:
        return redirect("/?acceso=1")
    if user["rol"] != "admin":
        return redirect("/cuenta/")
    return html_file("index.html")


@never_cache
@require_safe
def account_page(request):
    user = current_user(request)
    if user is None:
        return redirect("/?acceso=1")
    if user["rol"] == "admin":
        return redirect("/panel/")
    return html_file("account.html")


@require_safe
def terms_page(request):
    return html_file("terms.html")


urlpatterns = [
    path("", index, name="index"),
    path("terminos/", terms_page),
    path("api/atencion/", contract_views.attention),
    path("api/contratos/cuentas/", contract_views.controls),
    path("api/contratos/operador/", contract_views.operator),
    path("api/contratos/politica/", contract_views.policy),
    path("api/contratos/feriados/", contract_views.holidays),
    path("api/contratos/", contract_views.agreements),
    path("api/contratos/<str:identifier>/", contract_views.agreement),
    path("api/contratos/<str:identifier>/condiciones/", contract_views.accepted_terms),
    path("api/contratos/<str:identifier>/archivos/", contract_views.upload),
    path("api/contratos/<str:identifier>/archivos/<uuid:file_id>/", contract_views.evidence),
    path("panel/", panel),
    path("cuenta/", account_page),
    path("api/catalogo/", portal_views.catalog),
    path("api/catalogo/servicios/<str:identifier>/", portal_views.public_service),
    path("api/auth/sesion/", auth_views.session),
    path("api/auth/login/", auth_views.login),
    path("api/auth/registro/", auth_views.register),
    path("api/auth/logout/", auth_views.logout),
    path("api/cuenta/", portal_views.account),
    path("api/cuenta/solicitudes/", portal_views.create_request),
    path("api/operaciones/", business_views.operations),
    path("api/cuenta/responder/", portal_views.answer_request),
    path("api/cuenta/perfil/", portal_views.save_profile),
    path("api/cuenta/servicios/", portal_views.save_service),
    path("api/estado/", state, name="state"),
    path("api/revisiones/", workflow_views.reviews),
    path("api/<str:resource>/<str:identifier>/revision/", workflow_views.review),
    path("api/profesionales/<str:identifier>/documentos/", workflow_views.documents),
    path("api/profesionales/<str:identifier>/documentos/<uuid:file_id>/", workflow_views.download),
    path("api/profesionales/<str:identifier>/disponibilidad/", workflow_views.availability),
    path("api/profesionales/<str:identifier>/entrevista/", workflow_views.interview),
    path("api/<str:resource>/", records, name="records"),
    path("api/<str:resource>/<str:identifier>/", records, name="record"),
]

# Solo los archivos públicos necesarios; nunca se expone la raíz del proyecto.
if settings.DEBUG:
    urlpatterns += [
        path("index.html", index),
        re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.PROJECT_DIR / "assets"}),
    ]
    for folder, filenames in {
        "js": ("script.js", "workflow.js", "public.js", "portal.js"),
        "css": ("style.css", "validation.css", "public.css"),
    }.items():
        urlpatterns += [
            path(f"{folder}/{filename}", serve, {
                "path": filename, "document_root": settings.PROJECT_DIR / folder,
            })
            for filename in filenames
        ]
    urlpatterns += staticfiles_urlpatterns()
