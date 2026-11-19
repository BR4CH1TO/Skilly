let publicSession = null;
let publicCsrf = "";
let publicCatalog = {servicios: [], profesionales: []};

function actualizarCatalogoPublico(catalogo) {
    publicCatalog = catalogo;
}
let activeCategory = "Todos";
let catalogOffset = 0;
const intentService = new URLSearchParams(location.search).get("servicio");
const escapeText = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pesos = value => new Intl.NumberFormat("es-CL",{style:"currency",currency:"CLP",maximumFractionDigits:0}).format(value);

async function publicApi(path, options = {}) {
    const response = await fetch(path,{credentials:"same-origin",cache:"no-store",...options,headers:{...(options.body && !(options.body instanceof FormData) ? {"Content-Type":"application/json"}:{}),...(options.method && options.method!=="GET" ? {"X-CSRFToken":publicCsrf}:{}),...(options.headers||{})},signal:AbortSignal.timeout(15000)});
    const data=await response.json();
    if(!response.ok) {const error=new Error(data.error||"No pudimos completar la operación.");error.status=response.status;throw error;}
    return data;
}

function openPublicDialog(html) {
    document.querySelector("#dialogContent").innerHTML=html;
    const dialog=document.querySelector("#publicDialog");
    if(!dialog.open)dialog.showModal();
}

function authDialog(mode="login",role="empresa") {
    const register=mode==="register";
    openPublicDialog(`<span class="overline">BIENVENIDO A SKILLY</span><h2 class="dialog-title" id="dialogTitle">${register ? "Crea tu próxima conexión." : "Qué bueno verte de nuevo."}</h2><p class="dialog-description">${register ? "Crea tu cuenta para solicitar servicios o comenzar tu recorrido como profesional." : "Ingresa a tu espacio para continuar con tus solicitudes y servicios."}</p><form id="authForm" class="access-form">${register ? `<label>Tipo de cuenta<select name="rol"><option value="empresa" ${role==="empresa"?"selected":""}>Empresa · quiero contratar servicios</option><option value="profesional" ${role==="profesional"?"selected":""}>Profesional · quiero ofrecer servicios</option></select></label><label>Nombre ${role==="profesional"?"completo":"o nombre de tu empresa"}<input name="nombre" autocomplete="organization" minlength="3" maxlength="150" required></label>`:""}<label>Correo electrónico<input name="correo" type="email" autocomplete="email" maxlength="254" required></label><label>Contraseña<input name="password" type="password" autocomplete="${register?"new-password":"current-password"}" ${register?'minlength="8"':""} maxlength="128" required></label>${register?'<small>Al menos 8 caracteres. Evita contraseñas comunes o solo numéricas.</small><label>Confirmar contraseña<input name="confirmar" type="password" autocomplete="new-password" required></label>':""}${register?'<label class="auth-consent"><input type="checkbox" name="mayorEdad" required> Declaro ser mayor de 18 años y tener facultades para contratar.</label><label class="auth-consent"><input type="checkbox" name="aceptoTerminos" required> He leído y acepto los <a href="/terminos/" target="_blank" rel="noopener">términos y condiciones de prueba</a>.</label>':""}<p class="form-error" id="authError" role="alert"></p><button class="button primary" type="submit">${register?"Crear mi cuenta":"Iniciar sesión"} ↗</button></form><p class="access-switch">${register?"¿Ya tienes cuenta?":"¿Primera vez en Skilly?"} <button class="link-button" data-auth="${register?"login":"register"}">${register?"Inicia sesión":"Crea tu cuenta"}</button></p>`);
    document.querySelector("#authForm").onsubmit=async event=>{
        event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type="submit"]'),data=Object.fromEntries(new FormData(form));
        if(register && data.password!==data.confirmar){document.querySelector("#authError").textContent="Las contraseñas no coinciden.";return;}
        delete data.confirmar;button.disabled=true;
        try{
            if(register){const policy=await publicApi('/api/contratos/politica/');data.hashTerminos=policy.sha256;data.aceptoTerminos=form.elements.aceptoTerminos.checked;data.mayorEdad=form.elements.mayorEdad.checked;}
            const result=await publicApi(`/api/auth/${register?"registro":"login"}/`,{method:"POST",body:JSON.stringify(data)});
            location.href=result.redirect+(intentService && result.user.rol==="empresa"?`?servicio=${encodeURIComponent(intentService)}`:"");
        }catch(error){document.querySelector("#authError").textContent=error.message;button.disabled=false;}
    };
}

function requestService(id) {
    if(!publicSession){history.replaceState(null,"",`/?servicio=${encodeURIComponent(id)}`);location.href=`/?acceso=1&servicio=${encodeURIComponent(id)}`;return;}
    if(publicSession.rol!=="empresa"){
        openPublicDialog('<h2 class="dialog-title" id="dialogTitle">Solicitudes para empresas</h2><p class="dialog-description">Las solicitudes se envían desde una cuenta de empresa. Puedes seguir explorando la vitrina desde tu cuenta actual.</p>');return;
    }
    location.href=`/cuenta/?servicio=${encodeURIComponent(id)}`;
}

function showPublicService(id) {
    const s=publicCatalog.servicios.find(s=>s.id===id);if(!s)return;
    openPublicDialog(`${s.demostracion?'<span class="demo-tag">Servicio de demostración</span>':""}<span class="overline">${escapeText(s.categoria)}</span><h2 class="dialog-title" id="dialogTitle">${escapeText(s.titulo)}</h2><p class="dialog-description">Por ${escapeText(s.profesionalNombre)}</p><div class="detail-block"><h3>Sobre este servicio</h3><p>${escapeText(s.descripcion)}</p></div><div class="detail-block"><h3>Qué incluye</h3><p>${escapeText(s.entregables)}</p></div><div class="detail-block"><h3>Duración estimada</h3><p>${escapeText(s.duracion)}</p></div><div class="card-bottom"><div class="card-price"><small>Valor publicado · CLP</small><strong>${pesos(s.precio)}</strong></div><button class="button primary" data-request="${escapeText(s.id)}">Solicitar servicio ↗</button></div>`);
}

function showPublicProfile(id) {
    const p=publicCatalog.profesionales.find(p=>p.id===id);if(!p)return;
    const services=publicCatalog.servicios.filter(s=>s.profesionalId===id);
    openPublicDialog(`${p.demostracion?'<span class="demo-tag">Perfil de demostración</span>':""}<span class="overline">PERFIL PROFESIONAL</span><h2 class="dialog-title" id="dialogTitle">${escapeText(p.nombre)}</h2><p class="dialog-description">${escapeText(p.profesion)} · ${escapeText(p.ubicacion)}</p><span class="verified-tag">✓ Proceso de validación completado</span><div class="detail-block"><p>${escapeText(p.resumen)}</p></div><div class="category-filters">${(p.habilidades||[]).map(h=>`<span class="category-chip">${escapeText(h)}</span>`).join("")}</div><div class="detail-block"><h3>Servicios publicados</h3>${services.map(s=>`<p><button class="link-button" data-service="${escapeText(s.id)}">${escapeText(s.titulo)} ↗</button></p>`).join("")||'<p>Este profesional aún no tiene servicios publicados.</p>'}</div>`);
}

function renderPublicCatalog() {
    const query=(document.querySelector("#searchInput")?.value||"").trim().toLocaleLowerCase("es");
    const services=publicCatalog.servicios;
    document.querySelector("#publicServices").innerHTML=services.map(s=>`<article class="service-card-public">${s.demostracion?'<span class="demo-tag">Demostración</span>':""}<span class="card-category">${escapeText(s.categoria)}</span><h3>${escapeText(s.titulo)}</h3><p>${escapeText(s.descripcion)}</p><div class="card-provider">${escapeText(s.profesionalNombre)} · Profesional validado</div><div class="card-bottom"><div class="card-price"><small>Valor publicado · CLP</small><strong>${pesos(s.precio)}</strong></div><button class="button outline" data-service="${escapeText(s.id)}">Ver servicio ↗</button></div></article>`).join("")||`<div class="empty-catalog">${query||activeCategory!=="Todos"?"No encontramos servicios con esos filtros. Prueba otra búsqueda.":"Estamos preparando nuevas conexiones. Los servicios aparecerán aquí cuando completen su revisión de publicación."}</div>`;
    document.querySelector("#catalogFeedback").textContent=services.length?`${services.length} servicio${services.length===1?"":"s"} disponible${services.length===1?"":"s"}`:"";
    const profiles=publicCatalog.profesionales;
    document.querySelector("#publicProfessionals").innerHTML=profiles.map(p=>`<article class="talent-card"><div class="talent-avatar" aria-hidden="true">${escapeText(p.nombre.split(/\s+/).slice(0,2).map(n=>n[0]).join(""))}</div>${p.demostracion?'<span class="demo-tag">Demostración</span>':""}<h3>${escapeText(p.nombre)}</h3><p>${escapeText(p.profesion)}<br>${escapeText(p.ubicacion)}</p><span class="verified-tag">✓ Proceso de validación completado</span><button class="button outline" data-profile="${escapeText(p.id)}">Conocer perfil ↗</button></article>`).join("")||'<div class="empty-catalog">Los perfiles aparecerán aquí al completar su proceso de validación.</div>';
}

async function logoutPublic() {
    try{await publicApi("/api/auth/logout/",{method:"POST"});location.href="/";}catch(error){alert(error.message);}
}

async function loadPublicSession() {
    const session=await publicApi("/api/auth/sesion/");publicSession=session.user;publicCsrf=session.csrfToken;
    if(publicSession){document.querySelector("#sessionActions").innerHTML=`<a class="button outline" href="${session.redirect}">${publicSession.rol==="admin"?"Panel de gestión":"Mi espacio"} ↗</a><button class="button text" data-logout>Cerrar sesión</button>`;}
    return session;
}

document.addEventListener("click",async event=>{
    const target=event.target.closest("[data-auth],[data-close-dialog],[data-service],[data-profile],[data-request],[data-category],[data-logout]");if(!target)return;
    if(target.hasAttribute("data-auth")){const mode=target.dataset.auth;authDialog(mode==="professional"?"register":mode,mode==="professional"?"profesional":"empresa");}
    if(target.hasAttribute("data-close-dialog"))document.querySelector("#publicDialog").close();
    if(target.hasAttribute("data-service"))showPublicService(target.dataset.service);
    if(target.hasAttribute("data-profile"))showPublicProfile(target.dataset.profile);
    if(target.hasAttribute("data-request"))requestService(target.dataset.request);
    if(target.hasAttribute("data-logout"))await logoutPublic();
    if(target.hasAttribute("data-category")){activeCategory=target.dataset.category;await loadCatalogPage(true);}
});
document.addEventListener("DOMContentLoaded",async()=>{
    try{
        await loadPublicSession();
        if(!document.querySelector("#publicServices"))return;
        await loadCatalogPage(true);
        document.querySelector("#catalogSearch").onsubmit=async event=>{event.preventDefault();await loadCatalogPage(true);};
        document.querySelector("#loadCatalogMore").onclick=()=>loadCatalogPage(false);
        if(new URLSearchParams(location.search).get("acceso") && !publicSession)authDialog();
    }catch(error){const feedback=document.querySelector("#catalogFeedback");if(feedback)feedback.textContent="No pudimos cargar la vitrina. Comprueba la conexión e inténtalo nuevamente.";}
});

let catalogRequest = 0;
async function loadCatalogPage(reset=false) {
    const serial=++catalogRequest;
    const more=document.querySelector("#loadCatalogMore");
    if(more)more.disabled=true;
    const offset=reset?0:catalogOffset+24;
    const query=document.querySelector("#searchInput")?.value||"";
    try {
        const data=await publicApi(`/api/catalogo/?limit=24&offset=${offset}&q=${encodeURIComponent(query)}&categoria=${encodeURIComponent(activeCategory)}`);
        if(serial!==catalogRequest)return;
        if(reset)publicCatalog=data;
        else { publicCatalog.servicios.push(...data.servicios);publicCatalog.profesionales.push(...data.profesionales);publicCatalog.pagination=data.pagination; }
        catalogOffset=offset;
        document.querySelector("#categoryFilters").innerHTML=["Todos",...(data.categorias||[])].map(c=>`<button class="category-chip ${c===activeCategory?"active":""}" aria-pressed="${c===activeCategory}" data-category="${escapeText(c)}">${escapeText(c)}</button>`).join("");
        renderPublicCatalog();
        document.querySelector("#catalogFeedback").textContent=`${publicCatalog.servicios.length} de ${data.pagination.totalServicios} servicios`;
        if(more)more.hidden=offset+24>=Math.max(data.pagination.totalServicios,data.pagination.totalProfesionales);
    } catch(error) {document.querySelector("#catalogFeedback").textContent=error.message;}
    finally {if(more && serial===catalogRequest)more.disabled=false;}
}
