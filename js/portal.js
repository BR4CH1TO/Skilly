let accountData = null;

function portalChecks(revision) {
    if(!revision)return '<p class="feedback">La revisión se generará cuando guardes tu perfil.</p>';
    return `<span class="status-tag">${escapeText(revision.etapa||revision.estado)}</span><p class="notice-public">${escapeText(revision.justificacion||revision.siguientePaso)}</p><ul class="portal-checks">${revision.comprobaciones.map(c=>`<li><strong>${c.resultado==="aprobado"?"✓":"○"} ${escapeText(c.nombre)}</strong><p>${escapeText(c.detalle)}</p></li>`).join("")}</ul>`;
}

function renderOwnRequests() {
    return accountData.solicitudes.map(s=>`<article class="request-item"><strong>${escapeText(s.servicioTitulo||"Solicitud de servicio")}</strong><p>${new Date(s.fecha).toLocaleString("es-CL")} · <span class="status-tag">${escapeText(s.estado)}</span></p>${accountData.rol==="empresa" && s.estado==="aceptada" && !(accountData.agendas||[]).some(a=>a.record.solicitudId===s.id && a.record.estado!=="cancelado") ? `<button class="button primary" data-book-request="${escapeText(s.id)}">Elegir horario</button>`:""}${accountData.rol==="profesional" && s.estado==="pendiente"?`<div class="portal-form-actions"><button class="button primary" data-answer="aceptada" data-id="${escapeText(s.id)}">Aceptar solicitud</button><button class="button outline" data-answer="rechazada" data-id="${escapeText(s.id)}">Rechazar solicitud</button></div>`:""}</article>`).join("")||'<p class="feedback">Todavía no tienes solicitudes. Las nuevas conexiones aparecerán aquí.</p>';
}

async function refreshAccount() {
    accountData=await publicApi("/api/cuenta/");
    actualizarCatalogoPublico(await publicApi("/api/catalogo/"));
    const p=accountData.profile;
    document.querySelector("#accountContent").innerHTML=`<header class="portal-intro"><div><span class="overline">MI ESPACIO · ${accountData.rol==="empresa"?"EMPRESA":"PROFESIONAL"}</span><h1>Hola, ${escapeText(p.nombre)}.</h1><p>${accountData.rol==="empresa"?"Encuentra talento, envía tus solicitudes y sigue cada conexión.":"Completa tu perfil, sigue tu validación y gestiona tus servicios."}</p></div><a class="button outline" href="/">Explorar servicios ↗</a></header><p class="form-error" id="portalError" role="alert"></p>${accountData.rol==="empresa"?`<section class="portal-panel"><h2>Tus solicitudes</h2>${renderOwnRequests()}</section>`:`<div class="portal-columns"><section class="portal-panel"><h2>Tu recorrido de validación</h2>${portalChecks(accountData.validacion?.revision)}<div class="portal-form-actions"><button class="button primary" id="editMyProfile">Completar perfil</button><button class="button outline" id="uploadMyDocument">Cargar documentos</button></div></section><section class="portal-panel"><h2>Documentos y entrevista</h2><p class="feedback">Tus archivos solo son accesibles desde tu cuenta y administración. La entrevista será gestionada por el equipo de validación.</p>${(p.documentos||[]).map(d=>`<p><a class="link-button" href="/api/profesionales/${encodeURIComponent(p.id)}/documentos/${encodeURIComponent(d.id)}/">${escapeText(d.nombre)}</a></p>`).join("")||'<p class="feedback">Aún no has cargado documentos.</p>'}${accountData.validacion?.entrevista?`<p class="notice-public">Entrevista: ${escapeText(accountData.validacion.entrevista.resultado)}<br>${escapeText(accountData.validacion.entrevista.observaciones)}</p>`:""}</section></div><section class="portal-panel"><div class="section-heading"><h2>Tus servicios</h2><button class="button primary" id="newOwnService">Crear servicio ↗</button></div>${accountData.servicios.map(s=>`<article class="portal-service"><h3>${escapeText(s.record.titulo)}</h3>${portalChecks(s.record.revision)}<button class="button outline" data-edit-service="${escapeText(s.record.id)}">Editar servicio</button></article>`).join("")||'<p class="feedback">Publica tu primer servicio. El sistema mostrará los requisitos pendientes antes de habilitarlo en la vitrina.</p>'}</section><section class="portal-panel"><h2>Solicitudes recibidas</h2>${renderOwnRequests()}</section>`}`;
    document.querySelector("#accountContent").insertAdjacentHTML("beforeend",renderServiceTracking());
    window.dispatchEvent(new Event("skilly:account-refreshed"));
    if(accountData.rol==="profesional") {
        document.querySelector("#editMyProfile").onclick=editOwnProfile;
        document.querySelector("#uploadMyDocument").onclick=uploadOwnDocument;
        document.querySelector("#newOwnService").onclick=()=>editOwnService();
        const availability=document.createElement("button");availability.className="button outline";availability.textContent="Gestionar disponibilidad";availability.onclick=editOwnAvailability;
        document.querySelector("#editMyProfile").parentElement.append(availability);
    }
}

async function portalSubmit(form,route,options) {
    const button=form.querySelector('button[type="submit"]');button.disabled=true;
    const error=form.querySelector('[role="alert"]');error.textContent="";
    try{await publicApi(route,options);await refreshAccount();document.querySelector("#publicDialog").close();}
    catch(e){error.textContent=e.message;button.disabled=false;}
}

async function ownRequestDialog(id) {
    let s=publicCatalog.servicios.find(s=>s.id===id);
    if(!s){try{s=(await publicApi(`/api/catalogo/servicios/${encodeURIComponent(id)}/`)).record;}catch(error){document.querySelector("#portalError").textContent=error.message;return;}}
    if(!s){document.querySelector("#portalError").textContent="El servicio seleccionado ya no está disponible. Puedes explorar otras opciones en la vitrina.";return;}
    openPublicDialog(`<span class="overline">UNA NUEVA CONEXIÓN</span><h2 class="dialog-title" id="dialogTitle">Solicitar servicio</h2><h3>${escapeText(s.titulo)}</h3><p class="dialog-description">${escapeText(s.profesionalNombre)} · ${pesos(s.precio)} CLP</p>${s.demostracion?'<p class="notice-public">Este es un servicio de demostración. La solicitud se guardará como parte de la prueba del sistema; no constituye un cobro.</p>':""}<form class="access-form" id="ownRequestForm"><label>Fecha y hora propuestas<input type="datetime-local" name="fecha" required></label><p class="form-error" role="alert"></p><button type="submit" class="button primary">Enviar solicitud ↗</button></form>`);
    const operationKey=crypto.randomUUID();
    document.querySelector("#ownRequestForm").onsubmit=async event=>{
        event.preventDefault();const form=event.currentTarget,date=new Date(new FormData(form).get("fecha"));
        if(!Number.isFinite(date.getTime())||date<=new Date()){form.querySelector('[role="alert"]').textContent="Selecciona una fecha futura.";return;}
        await portalSubmit(form,"/api/cuenta/solicitudes/",{method:"POST",body:JSON.stringify({servicioId:id,fecha:date.toISOString(),claveOperacion:operationKey})});
    };
}

function editOwnProfile() {
    const p=accountData.profile;
    openPublicDialog(`<h2 class="dialog-title" id="dialogTitle">Tu perfil profesional</h2><form id="ownProfileForm" class="access-form"><label>Profesión<input name="profesion" value="${escapeText(p.profesion)}" required minlength="3" maxlength="150"></label><label>Ubicación<input name="ubicacion" value="${escapeText(p.ubicacion)}" required maxlength="150"></label><label>Experiencia<input name="experiencia" value="${escapeText(p.experiencia||"")}" maxlength="150" placeholder="Por ejemplo: 5 años"></label><label>Presentación<textarea name="resumen" required minlength="40" maxlength="4000">${escapeText(p.resumen)}</textarea></label><label>Habilidades, separadas por comas<input name="habilidades" value="${escapeText((p.habilidades||[]).join(", "))}" required maxlength="500"></label><p class="form-error" role="alert"></p><button type="submit" class="button primary">Guardar y revisar</button></form>`);
    document.querySelector("#ownProfileForm").onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,record=Object.fromEntries(new FormData(form));record.habilidades=record.habilidades.split(",").map(s=>s.trim()).filter(Boolean);await portalSubmit(form,"/api/cuenta/perfil/",{method:"PUT",body:JSON.stringify({record,version:accountData.version})});};
}

function uploadOwnDocument() {
    openPublicDialog('<h2 class="dialog-title" id="dialogTitle">Documentación profesional</h2><p class="dialog-description">Adjunta tu currículum y un respaldo de formación o experiencia. PDF hasta 5 MiB. La comprobación de formato no acredita autenticidad.</p><form id="ownDocumentForm" class="access-form"><label>Tipo<select name="tipo"><option value="cv">Currículum</option><option value="formacion">Respaldo de formación o experiencia</option></select></label><label>Archivo<input type="file" name="archivo" accept="application/pdf,.pdf" required></label><p class="form-error" role="alert"></p><button type="submit" class="button primary">Cargar y revisar</button></form>');
    document.querySelector("#ownDocumentForm").onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,body=new FormData(form);body.set("version",accountData.version);await portalSubmit(form,`/api/profesionales/${encodeURIComponent(accountData.profile.id)}/documentos/`,{method:"POST",body});};
}

function editOwnService(id=null) {
    const existing=accountData.servicios.find(s=>s.record.id===id),s=existing?.record||{};
    openPublicDialog(`<h2 class="dialog-title" id="dialogTitle">${id?"Editar":"Crear"} servicio</h2><p class="dialog-description">El servicio será visible en la vitrina cuando su revisión y tu validación estén completas.</p><form id="ownServiceForm" class="access-form"><label>Título<input name="titulo" value="${escapeText(s.titulo)}" minlength="8" maxlength="200" required></label><label>Categoría<input name="categoria" value="${escapeText(s.categoria)}" maxlength="100" required></label><label>Descripción<textarea name="descripcion" minlength="40" maxlength="4000" required>${escapeText(s.descripcion)}</textarea></label><label>Entregables<textarea name="entregables" minlength="15" maxlength="4000" required>${escapeText(s.entregables)}</textarea></label><label>Duración estimada<input name="duracion" value="${escapeText(s.duracion)}" maxlength="100" required></label><label>Precio en CLP<input type="number" min="1" step="1" name="precio" value="${escapeText(s.precio)}" required></label><p class="form-error" role="alert"></p><button type="submit" class="button primary">Guardar y revisar</button></form>`);
    document.querySelector("#ownServiceForm").onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,record=Object.fromEntries(new FormData(form));record.precio=Number(record.precio);await portalSubmit(form,"/api/cuenta/servicios/",{method:id?"PUT":"POST",body:JSON.stringify({record,id,version:existing?.version})});};
}

document.addEventListener("click",async event=>{
    const edit=event.target.closest("[data-edit-service]");if(edit)editOwnService(edit.dataset.editService);
    const answer=event.target.closest("[data-answer]");
    if(answer){answer.disabled=true;try{await publicApi("/api/cuenta/responder/",{method:"POST",body:JSON.stringify({id:answer.dataset.id,estado:answer.dataset.answer})});await refreshAccount();}catch(e){document.querySelector("#portalError").textContent=e.message;answer.disabled=false;}}
});
document.addEventListener("DOMContentLoaded",async()=>{
    try{await loadPublicSession();if(!publicSession){location.href="/?acceso=1";return;}await refreshAccount();if(intentService && accountData.rol==="empresa")await ownRequestDialog(intentService);}
    catch(error){if(error.status===401){location.href="/?acceso=1";return;}document.querySelector("#accountContent").textContent=error.message;}
});

function renderServiceTracking() {
    const role=accountData.rol;
    const cards=(accountData.agendas||[]).filter(({record:a})=>!a.contratoRequerido&&!a.contratoId).map(({record:a,version})=>{
        const controls=[];
        if(role==="profesional" && a.estado==="propuesto")controls.push(["confirmar","Confirmar horario"]);
        if(role==="profesional" && a.estado==="confirmado")controls.push(["realizar","Marcar como realizado"]);
        if(role==="empresa" && a.estado==="realizado" && a.pagoEstado==="pendiente")controls.push(["pagar","Simular pago"]);
        if(role==="empresa" && a.estado==="realizado" && a.pagoEstado==="pagado")controls.push(["finalizar","Finalizar servicio"]);
        if(role==="empresa" && a.estado==="finalizado" && !a.evaluacion)controls.push(["evaluar","Evaluar servicio"]);
        if(["propuesto","confirmado"].includes(a.estado))controls.push(["cancelar","Cancelar horario"]);
        return `<article class="request-item"><h3>${escapeText(accountData.solicitudes.find(s=>s.id===a.solicitudId)?.servicioTitulo||"Servicio contratado")}</h3><p>${new Date(a.fecha).toLocaleString("es-CL")} · <span class="status-tag">${escapeText(a.estado)}</span></p><p>Valor acordado: ${pesos(a.precioAcordado||0)} · Seguimiento: ${escapeText(a.pagoEstado||"espera")}</p><p class="feedback">Pago demostrativo; no se realiza ningún cobro.</p>${a.evaluacion?`<p>Evaluación: ${a.evaluacion.nota}/5 · ${escapeText(a.evaluacion.comentario)}</p>`:""}<div class="portal-form-actions">${controls.map(([action,label])=>`<button class="button ${action==="cancelar"?"outline":"primary"}" data-agenda-operation="${action}" data-agenda="${escapeText(a.id)}" data-version="${version}">${label}</button>`).join("")}</div></article>`;
    }).join("");
    return `<section class="portal-panel"><h2>Seguimiento de servicios</h2>${cards||'<p class="feedback">Los horarios y avances aparecerán aquí después de agendar una solicitud aceptada.</p>'}</section>`;
}
function bookingDialog(id) {
    const request=accountData.solicitudes.find(s=>s.id===id);if(!request)return;
    const slots=request.horariosDisponibles||[];
    openPublicDialog(`<h2 class="dialog-title" id="dialogTitle">Elige un horario</h2><p class="dialog-description">El profesional confirmará tu propuesta. Solo se muestran horarios futuros disponibles.</p>${slots.length?`<form id="bookingForm" class="access-form"><label>Horario<select name="fecha">${slots.map(s=>`<option value="${escapeText(s)}">${new Date(s).toLocaleString("es-CL")}</option>`).join("")}</select></label><p class="form-error" role="alert"></p><button type="submit" class="button primary">Proponer horario</button></form>`:'<p class="notice-public">El profesional aún no tiene horarios disponibles. Podrás agendar cuando actualice su disponibilidad.</p>'}`);
    if(slots.length){const key=crypto.randomUUID();document.querySelector("#bookingForm").onsubmit=async e=>{e.preventDefault();await portalSubmit(e.currentTarget,"/api/operaciones/",{method:"POST",body:JSON.stringify({accion:"agendar",solicitudId:id,fecha:new FormData(e.currentTarget).get("fecha"),claveOperacion:key})});};}
}
function editOwnAvailability() {
    const values=(accountData.profile.disponibilidad||[]).filter(s=>new Date(s)>new Date());
    openPublicDialog('<h2 class="dialog-title" id="dialogTitle">Tu disponibilidad</h2><p class="dialog-description">Publica hasta 100 horarios dentro de los próximos 180 días. Los horarios ya contratados conservan su seguimiento.</p><form id="availabilityForm" class="access-form"><label>Añadir fecha y hora<input id="newAvailabilitySlot" type="datetime-local"></label><button type="button" class="button outline" id="addAvailabilitySlot">Añadir horario</button><ul id="availabilitySlots" class="portal-checks"></ul><p class="form-error" role="alert"></p><button type="submit" class="button primary">Guardar disponibilidad</button></form>');
    const render=()=>{document.querySelector("#availabilitySlots").innerHTML=values.map((s,i)=>`<li>${new Date(s).toLocaleString("es-CL")} <button type="button" class="link-button" data-remove-slot="${i}">Quitar</button></li>`).join("");};render();
    document.querySelector("#availabilitySlots").onclick=e=>{const b=e.target.closest("[data-remove-slot]");if(b){values.splice(Number(b.dataset.removeSlot),1);render();}};
    document.querySelector("#addAvailabilitySlot").onclick=()=>{const input=document.querySelector("#newAvailabilitySlot"),date=new Date(input.value);if(Number.isFinite(date.getTime())&&date>new Date()&&!values.includes(date.toISOString())){values.push(date.toISOString());values.sort((a,b)=>Date.parse(a)-Date.parse(b));input.value="";render();}};
    document.querySelector("#availabilityForm").onsubmit=async e=>{e.preventDefault();await portalSubmit(e.currentTarget,"/api/cuenta/perfil/",{method:"PUT",body:JSON.stringify({version:accountData.version,record:{disponibilidad:values}})});};
}
document.addEventListener("click",async e=>{
    const book=e.target.closest("[data-book-request]");if(book)bookingDialog(book.dataset.bookRequest);
    const op=e.target.closest("[data-agenda-operation]");if(!op)return;
    const data={agendaId:op.dataset.agenda,version:Number(op.dataset.version),accion:op.dataset.agendaOperation};
    if(data.accion==="evaluar"){
        openPublicDialog('<h2 class="dialog-title" id="dialogTitle">Evaluar servicio</h2><form id="evaluationForm" class="access-form"><label>Nota<select name="nota"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select></label><label>Comentario<textarea name="comentario" minlength="3" maxlength="1000" required></textarea></label><p class="form-error" role="alert"></p><button class="button primary" type="submit">Guardar evaluación</button></form>');
        document.querySelector("#evaluationForm").onsubmit=async event=>{event.preventDefault();const v=Object.fromEntries(new FormData(event.currentTarget));data.evaluacion={nota:Number(v.nota),comentario:v.comentario};await portalSubmit(event.currentTarget,"/api/operaciones/",{method:"POST",body:JSON.stringify(data)});};return;
    }
    if(data.accion==="cancelar" && !confirm("¿Confirmas que deseas cancelar este horario?"))return;
    op.disabled=true;
    try{await publicApi("/api/operaciones/",{method:"POST",body:JSON.stringify(data)});await refreshAccount();}
    catch(error){document.querySelector("#portalError").textContent=error.message;op.disabled=false;}
});
