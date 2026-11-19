let validacionSeleccionada = null;

function comprobacionesHTML(revision) {
    if (!revision) return '<p class="notice">Todavía no hay una revisión registrada.</p>';
    const checks = revision.comprobaciones;
    const aprobadas = checks.filter(c => c.resultado === "aprobado");
    const pendientes = checks.filter(c => c.resultado !== "aprobado");
    const tarjeta = c => {
        const ok = c.resultado === "aprobado";
        const rechazado = c.resultado === "rechazado";
        return `<li class="review-item ${ok ? "is-approved" : rechazado ? "is-rejected" : "is-pending"}">
            <span class="review-item-icon" aria-hidden="true">${ok ? "✓" : rechazado ? "×" : "!"}</span>
            <div class="review-item-content"><div class="review-item-heading"><h4>${escaparHTML(c.nombre)}</h4><span class="review-pill ${ok ? "approved" : rechazado ? "rejected" : "pending"}">${ok ? "Aprobado" : rechazado ? "Rechazado" : "Pendiente"}</span></div>
            <p>${escaparHTML(c.detalle)}</p><details class="review-rule"><summary>Ver criterio evaluado</summary><p>Referencia ${escaparHTML(c.codigo)} · ${escaparHTML(c.detalle)}</p></details></div></li>`;
    };
    return `${revision.demostracion ? '<p class="review-demo">Caso de demostración · ejemplo del recorrido de validación.</p>' : ''}
        ${revision.justificacion ? `<section class="review-decision ${revision.estado === "validado" ? "decision-approved" : revision.estado === "rechazado" ? "decision-rejected" : "decision-pending"}"><span class="review-kicker">RESULTADO DEL SISTEMA</span><h3>${revision.estado === "validado" ? "Profesional aprobado" : revision.estado === "rechazado" ? "Profesional rechazado" : "Validación pendiente"}</h3><p>${escaparHTML(revision.justificacion)}</p></section>` : ''}
        <section class="review-overview" aria-label="Avance de la revisión">
        <div class="review-overview-top"><span class="review-kicker">AVANCE DEL PROCESO</span><span class="review-pill ${revision.estado === "rechazado" ? "rejected" : pendientes.length ? "pending" : "approved"}">${revision.estado === "rechazado" ? "No aprobado" : pendientes.length ? "En curso" : "Completado"}</span></div>
        <div class="review-score"><strong>${aprobadas.length}<span> / ${checks.length}</span></strong><span>comprobaciones<br>aprobadas</span></div>
        <progress class="review-progress" value="${aprobadas.length}" max="${checks.length}" aria-label="${aprobadas.length} de ${checks.length} comprobaciones aprobadas"></progress>
        <div class="review-next"><span class="review-next-icon" aria-hidden="true">→</span><div><strong>Siguiente paso</strong><p>${escaparHTML(revision.siguientePaso)}</p></div></div>
        <div class="review-owner"><span>Responsable de la próxima acción</span><strong>${escaparHTML(revision.responsable)}</strong></div>
        </section>
        ${pendientes.length ? `<section class="review-group"><div class="review-section-title"><h3>${revision.estado === "rechazado" ? "Motivo de no aprobación" : "Pendientes para avanzar"}</h3><span>${pendientes.length}</span></div><ul class="review-items">${pendientes.map(tarjeta).join("")}</ul></section>` : ''}
        ${aprobadas.length ? `<details class="review-completed" ${pendientes.length ? '' : 'open'}><summary><span class="review-completed-mark" aria-hidden="true">✓</span> Comprobaciones aprobadas <span class="review-count">${aprobadas.length}</span></summary><ul class="review-items">${aprobadas.map(tarjeta).join("")}</ul></details>` : ''}
        <details class="review-audit"><summary>Información de la revisión</summary><dl><div><dt>Última revisión</dt><dd>${escaparHTML(formatoFecha(revision.fecha))}</dd></div><div><dt>Versión de criterios</dt><dd>${escaparHTML(revision.reglasVersion)}</dd></div></dl><p>${escaparHTML(revision.alcance)}</p></details>`;
}

function etapasValidacionHTML(revision) {
    const checks = revision?.comprobaciones || [];
    const completo = prefijo => checks.some(c=>c.codigo.startsWith(prefijo)) && checks.filter(c=>c.codigo.startsWith(prefijo)).every(c=>c.resultado === "aprobado");
    const etapas = [{nombre:"Perfil",ok:completo("PER-")},{nombre:"Documentos",ok:completo("DOC-")},{nombre:"Entrevista online",ok:completo("ENT-")},{nombre:"Validación",ok:revision?.estado === "validado"}];
    const actual = etapas.findIndex(e=>!e.ok);
    return `<ol class="validation-stepper" aria-label="Etapas de validación">${etapas.map((e,i)=>`<li class="${e.ok ? "is-complete" : i === actual ? "is-current" : "is-waiting"}" ${i===actual ? 'aria-current="step"' : ''}><span class="step-number" aria-hidden="true">${e.ok ? "✓" : i+1}</span><span class="step-label">${e.nombre}<small>${e.ok ? "Completado" : i===actual ? "Etapa actual" : "Por completar"}</small></span></li>`).join("")}</ol>`;
}

function renderizarValidaciones() {
    $("#validationList").innerHTML = profesionales.map(p => {
        const v = validaciones.find(v => v.profesionalId === p.id);
        const pendientes = v?.revision?.comprobaciones.filter(c => c.resultado !== "aprobado").length;
        return `<button class="validation-card" data-action="ver-validacion" data-id="${escaparHTML(p.id)}"><div class="avatar">${escaparHTML(p.iniciales || "SK")}</div><div><h3>${escaparHTML(p.nombre)}</h3><p>${escaparHTML(v?.etapa || "Pendiente de revisión")}</p><small>${pendientes ?? "—"} comprobaciones pendientes</small></div><span class="status ${obtenerClaseEstado(p.estado)}">${escaparHTML(obtenerTextoEstado(p.estado))}</span></button>`;
    }).join("") || '<p class="notice">Registra un profesional para iniciar su recorrido.</p>';
    if (validacionSeleccionada) mostrarValidacion(validacionSeleccionada);
}

function mostrarValidacion(id) {
    validacionSeleccionada = id;
    const profesional = obtenerProfesional(id);
    const validacion = validaciones.find(v => v.profesionalId === id);
    if (!profesional) return;
    const entrevista = validacion?.entrevista;
    $("#validationDetail").classList.remove("empty");
    $("#validationDetail").classList.add("validation-workspace");
    $("#validationDetail").innerHTML = `<header class="validation-person"><div class="validation-person-avatar" aria-hidden="true">${escaparHTML(profesional.iniciales || "SK")}</div><div><span class="review-kicker">VALIDACIÓN PROFESIONAL</span><h2>${escaparHTML(profesional.nombre)}</h2><p>${escaparHTML(profesional.profesion)}</p></div></header>
        ${etapasValidacionHTML(validacion?.revision)}
        ${comprobacionesHTML(validacion?.revision)}
        <section class="validation-support"><h3>Documentación</h3>${(profesional.documentos || []).map(d => `<p><strong>${escaparHTML(d.tipo === "cv" ? "Currículum" : "Respaldo profesional")}</strong> · <a href="/api/profesionales/${encodeURIComponent(id)}/documentos/${encodeURIComponent(d.id)}/">${escaparHTML(d.nombre)}</a><br><small>Formato comprobado · autenticidad no verificada · ${escaparHTML(formatoFecha(d.fecha))}</small></p>`).join("") || '<p>Aún no se han cargado documentos. Añade el currículum y el respaldo profesional para continuar.</p>'}
        </section><section class="validation-support"><h3>Entrevista online</h3>${entrevista ? `<p>${escaparHTML(entrevista.resultado)} · ${escaparHTML(formatoFecha(entrevista.fecha))}</p><p>Responsable: ${escaparHTML(entrevista.responsable)}</p><p>${escaparHTML(entrevista.observaciones)}</p>` : '<p>La entrevista se habilitará cuando estén completos el perfil y la documentación.</p>'}
        </section><div class="modal-actions validation-actions"><button class="btn ghost" data-action="editar-profesional" data-id="${escaparHTML(id)}">Completar perfil</button><button class="btn ghost" data-action="subir-documentos" data-id="${escaparHTML(id)}">Cargar documentos</button><button class="btn primary" data-action="revisar-profesional" data-id="${escaparHTML(id)}">Revisar automáticamente</button><button class="btn ghost" data-action="registrar-entrevista" data-id="${escaparHTML(id)}">Gestionar entrevista</button><button class="btn ghost" data-action="historial-profesional" data-id="${escaparHTML(id)}">Ver historial de revisiones</button></div>`;
}

async function refrescarWorkflow() {
    await cargarEstado();
    llenarProfesionalesCalendario();
    actualizarResumen(); renderizarProfesionales(); renderizarEmpresas(); renderizarValidaciones();
    renderizarServicios(); renderizarSolicitudes(); renderizarCalendario(); renderizarAgendamientos();
    renderizarPagos(); renderizarTrazabilidad(); renderizarActividadInicio();
}

async function ejecutarWorkflow(ruta, opciones = {}, despues = null) {
    const errorPanel = $("#workflowError");
    if (errorPanel) errorPanel.textContent = "";
    try {
        if (guardadoPendiente) await colaGuardado;
        establecerGuardadoPendiente(true);
        mostrarConexion("Procesando y guardando la revisión…");
        await solicitarEstado({method: "POST", ...opciones, headers: {"X-CSRFToken": csrfToken, ...(opciones.headers || {})}}, ruta);
        await refrescarWorkflow();
        cerrarModal();
        if (despues) despues();
        mostrarToast("Proceso guardado. Puedes consultar sus comprobaciones.");
    } catch (error) {
        const mensaje = `${error.message} Si se interrumpió la conexión, recarga para comprobar lo guardado.`;
        if (errorPanel?.isConnected) errorPanel.textContent = mensaje;
        else mostrarToast(mensaje);
    } finally {
        establecerGuardadoPendiente(false);
        $("#databaseStatus")?.close();
    }
}

function formularioError() { return '<p id="workflowError" class="workflow-error" role="alert"></p>'; }
function campo(nombre, etiqueta, valor = "", extra = "") {
    return `<label>${etiqueta}<input name="${nombre}" value="${escaparHTML(valor)}" ${extra}></label>`;
}

function editarProfesional(id = null) {
    const p = id ? obtenerProfesional(id) : {};
    abrirModal(`<h1 id="modalTitle">${id ? "Completar perfil" : "Registrar profesional"}</h1><p>El sistema comprobará los requisitos al guardar. No se puede seleccionar manualmente «Validado».</p>
        <form id="professionalForm" class="form">${campo("nombre", "Nombre completo", p.nombre, 'required minlength="3" maxlength="150"')}${campo("profesion", "Profesión", p.profesion, 'required minlength="3" maxlength="150"')}${campo("ubicacion", "Ubicación", p.ubicacion, 'required minlength="3" maxlength="150"')}
        <label>Presentación profesional<textarea name="resumen" required minlength="40" maxlength="4000">${escaparHTML(p.resumen || "")}</textarea></label>${campo("habilidades", "Habilidades, separadas por comas", (p.habilidades || []).join(", "), 'required maxlength="500"')}
        ${formularioError()}<button class="btn primary">Guardar y revisar</button></form>`);
    $("#professionalForm").onsubmit = async evento => {
        evento.preventDefault(); const datos = Object.fromEntries(new FormData(evento.currentTarget));
        const registro = {...p, ...datos, id: id || nuevoId(), habilidades: datos.habilidades.split(",").map(s => s.trim()).filter(Boolean), estado: p.estado || "revision"};
        if (!id) Object.assign(registro, {iniciales: datos.nombre.split(/\s+/).slice(0,2).map(n=>n[0]).join(""), experiencia: "No informada", habilidades: registro.habilidades, experienciaLaboral: [], educacion: [], cursos: [], disponibilidad: [], serviciosRealizados: 0, empresas: 0, cumplimiento: "Sin historial"});
        await ejecutarWorkflow(`/api/profesionales/${id ? encodeURIComponent(id) + "/" : ""}`, {method: id ? "PUT" : "POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({record:registro,version:versiones.profesionales?.[id]})}, () => {irA("validaciones"); mostrarValidacion(registro.id);});
    };
}

function subirDocumentos(id) {
    abrirModal(`<h1 id="modalTitle">Documentación del profesional</h1><p>Requisitos iniciales: currículum y respaldo de formación o experiencia. Solo PDF de hasta 5 MiB. Se comprueba la estructura PDF, el tamaño y la ausencia de acciones automáticas. No certifica autenticidad ni contenido.</p><form id="documentForm" class="form"><label>Tipo<select name="tipo"><option value="cv">Currículum</option><option value="formacion">Respaldo de formación o experiencia</option></select></label><label>Archivo PDF<input type="file" name="archivo" accept="application/pdf,.pdf" required></label>${formularioError()}<button class="btn primary">Cargar y revisar</button></form>`);
    $("#documentForm").onsubmit = async evento => {
        evento.preventDefault(); const datos = new FormData(evento.currentTarget); datos.set("version", versiones.profesionales[id]);
        await ejecutarWorkflow(`/api/profesionales/${encodeURIComponent(id)}/documentos/`, {body:datos}, () => mostrarValidacion(id));
    };
}

function registrarEntrevista(id) {
    const v = validaciones.find(v=>v.profesionalId===id); const anterior = v?.entrevista || {};
    abrirModal(`<h1 id="modalTitle">Gestión de entrevista online</h1><p>Agenda la entrevista y registra su resultado cuando el profesional haya completado los requisitos previos.</p><form id="interviewForm" class="form">${campo("responsable", "Responsable de la entrevista", anterior.responsable, 'required minlength="3" maxlength="150"')}${campo("fecha", "Fecha y hora de la entrevista", "", 'type="datetime-local" required')}${campo("enlace", "Enlace de la reunión online", anterior.enlace, 'type="url" placeholder="https://…" required')}<label>Acción / resultado<select name="resultado"><option value="agendada">Agendar entrevista</option><option value="aprobada">Entrevista realizada: aprobada</option><option value="segunda">Entrevista realizada: segunda entrevista</option><option value="rechazada">Entrevista realizada: rechazada</option></select></label><label>Observaciones<textarea name="observaciones" minlength="10" maxlength="4000" required></textarea></label>${formularioError()}<button class="btn primary">Guardar entrevista</button></form>`);
    $("#interviewForm").onsubmit = async evento => {
        evento.preventDefault(); const datos=Object.fromEntries(new FormData(evento.currentTarget)); 
        datos.fecha=new Date(datos.fecha).toISOString();datos.version=versiones.validaciones[id];
        await ejecutarWorkflow(`/api/profesionales/${encodeURIComponent(id)}/entrevista/`, {headers:{"Content-Type":"application/json"},body:JSON.stringify(datos)},()=>mostrarValidacion(id));
    };
}

function editarServicio(id = null) {
    const s=id ? obtenerServicio(id) : {};
    abrirModal(`<h1 id="modalTitle">${id ? "Corregir servicio" : "Publicar servicio"}</h1><p>El sistema revisará el contenido y la validación del profesional. Podrás ver el resultado de cada comprobación.</p><form id="servicePublishForm" class="form"><label>Profesional<select name="profesionalId" required>${profesionales.map(p=>`<option value="${escaparHTML(p.id)}" ${p.id===s.profesionalId ? "selected" : ""}>${escaparHTML(p.nombre)}</option>`).join("")}</select></label>${campo("titulo", "Título", s.titulo, 'required minlength="8" maxlength="200"')}${campo("categoria", "Categoría", s.categoria, 'required maxlength="100"')}<label>Descripción<textarea name="descripcion" required minlength="40" maxlength="4000">${escaparHTML(s.descripcion || "")}</textarea></label><label>Entregables<textarea name="entregables" required minlength="15" maxlength="4000">${escaparHTML(s.entregables || "")}</textarea></label>${campo("duracion", "Duración estimada", s.duracion, 'required maxlength="100"')}${campo("precio", "Precio en pesos chilenos", s.precio ?? "", 'type="number" min="1" step="1" required')}${formularioError()}<button class="btn primary">Enviar a revisión automática</button></form>`);
    $("#servicePublishForm").onsubmit=async evento=>{
        evento.preventDefault();const datos=Object.fromEntries(new FormData(evento.currentTarget)); const record={...s,...datos,id:id || nuevoId(),precio:Number(datos.precio),disponible:false};
        await ejecutarWorkflow(`/api/servicios/${id ? encodeURIComponent(id)+"/" : ""}`,{method:id ? "PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({record,version:versiones.servicios?.[id]})},()=>abrirServicio(record.id));
    };
}

async function verHistorialRevision(recurso, id) {
    try {
        const datos=await solicitarEstado({},`/api/revisiones/?recurso=${encodeURIComponent(recurso)}&id=${encodeURIComponent(id)}`);
        abrirModal(`<h1 id="modalTitle">Historial de revisiones</h1>${datos.results.map(r=>`<article class="timeline-item"><strong>${escaparHTML(formatoFecha(r.fecha))} · ${escaparHTML(r.actor)}</strong>${r.resultado.comprobaciones ? comprobacionesHTML(r.resultado) : `<p>${r.resultado.tipo === "disponibilidad" ? "Disponibilidad" : "Entrevista"}: ${escaparHTML(r.resultado.resultado)} · ${escaparHTML(r.resultado.observaciones)}</p>`}</article>`).join("") || '<p>Sin revisiones registradas.</p>'}`);
    } catch(error) {mostrarToast(error.message);}
}

 document.querySelector("#adminLogout")?.addEventListener("click", async () => {
    try { await solicitarEstado({method:"POST",headers:{"X-CSRFToken":csrfToken}},"/api/auth/logout/"); location.href="/"; }
    catch(error) { mostrarToast(error.message); }
});
