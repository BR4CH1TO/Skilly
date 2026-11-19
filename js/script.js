let solicitudes = [];
let agendamientos = [];
let pagos = [];
let trazabilidad = [];
let profesionales = [];
let empresas = [];
let validaciones = [];
let servicios = [];
let versiones = {};
let estadoConfirmado = {};
let operacionesPendientes = 0;
const colecciones = {
    profesionales: "profesionales", empresas: "empresas", validaciones: "validaciones",
    servicios: "servicios", solicitudes: "solicitudes", agendamientos: "agendas",
    pagos: "pagos", trazabilidad: "historial"
};
let csrfToken = "";
let guardadoPendiente = false;

function establecerGuardadoPendiente(pendiente) {
    guardadoPendiente = pendiente;
}
let colaGuardado = Promise.resolve();

function estadoActual() {
    return { profesionales, empresas, validaciones, servicios,
        solicitudes, agendamientos, pagos, trazabilidad };
}

function mostrarConexion(mensaje, error = false) {
    let dialogo = document.querySelector("#databaseStatus");
    if (!dialogo) {
        dialogo = document.createElement("dialog");
        dialogo.id = "databaseStatus";
        dialogo.setAttribute("aria-label", "Conexión con los datos");
        dialogo.addEventListener("cancel", evento => evento.preventDefault());
        document.body.append(dialogo);
    }
    dialogo.replaceChildren();
    const texto = document.createElement("p");
    texto.textContent = mensaje;
    dialogo.append(texto);
    if (error) {
        const boton = document.createElement("button");
        boton.className = "btn primary";
        boton.textContent = "Recargar datos del servidor";
        boton.onclick = () => location.reload();
        dialogo.append(boton);
    }
    if (!dialogo.open) dialogo.showModal();
}

async function solicitarEstado(opciones = {}, ruta = "/api/estado/") {
    const respuesta = await fetch(ruta, {
        credentials: "same-origin", cache: "no-store", ...opciones,
        signal: AbortSignal.timeout(15000)
    });
    const datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error || "No fue posible guardar los datos.");
    return datos;
}

const clasesEstado = {
    validado: "validado",
    revision: "revision",
    segunda: "segunda",
    pendiente: "pendiente",
    aceptada: "aceptada",
    rechazada: "rechazada",
    rechazado: "rechazada",
    expirada: "expirada",
    propuesto: "propuesto",
    confirmado: "confirmado",
    pagado: "pagado",
    activa: "activa",
    espera: "espera",
    realizado: "realizado",
    finalizado: "finalizado",
    inactiva: "inactiva"
};


const textosEstado = {
    validado: "Validado",
    revision: "En revisión",
    segunda: "Segunda entrevista",
    pendiente: "Pendiente",
    aceptada: "Aceptada",
    rechazada: "Rechazada",
    rechazado: "Rechazado",
    expirada: "Expirada",
    propuesto: "Propuesto",
    confirmado: "Confirmado",
    pagado: "Pagado",
    activa: "Activa",
    espera: "En espera del servicio",
    realizado: "Servicio realizado",
    finalizado: "Finalizado",
    inactiva: "Inactiva"
};


const transicionesSolicitud = {
    pendiente: ["aceptada", "rechazada"],
    aceptada: [],
    rechazada: [],
    expirada: []
};


function copiar(valor) {
    return JSON.parse(JSON.stringify(valor));
}


function $(selector) {
    return document.querySelector(selector);
}


function $$(selector) {
    return [...document.querySelectorAll(selector)];
}


function escaparHTML(valor) {
    return String(valor ?? "").replace(
        /[&<>"']/g,
        caracter => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[caracter]
    );
}


function urlSegura(valor) {
    if (!valor) {
        return "";
    }

    try {
        const url = new URL(valor);

        if (url.protocol !== "https:") {
            return "";
        }

        return url.href;
    } catch {
        return "";
    }
}


function normalizar(valor) {
    return String(valor ?? "")
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .trim();
}


function debounce(funcion, espera = 180) {
    let temporizador;

    return (...argumentos) => {
        clearTimeout(temporizador);

        temporizador = setTimeout(
            () => funcion(...argumentos),
            espera
        );
    };
}


function nuevoId() {
    if (crypto.randomUUID) {
        return crypto.randomUUID();
    }

    return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
}


function obtenerProfesional(id) {
    return profesionales.find(
        profesional => profesional.id === id
    );
}


function obtenerEmpresa(id) {
    return empresas.find(
        empresa => empresa.id === id
    );
}


function obtenerServicio(id) {
    return servicios.find(
        servicio => servicio.id === id
    );
}


function obtenerSolicitud(id) {
    return solicitudes.find(
        solicitud => solicitud.id === id
    );
}


function formatoMoneda(valor) {
    return new Intl.NumberFormat(
        "es-CL",
        {
            style: "currency",
            currency: "CLP",
            maximumFractionDigits: 0
        }
    ).format(valor);
}


function formatoFecha(fecha) {
    if (!fecha) {
        return "";
    }

    const date = new Date(fecha);

    return new Intl.DateTimeFormat(
        "es-CL",
        {
            dateStyle: "short",
            timeStyle: "short"
        }
    ).format(date);
}


function formatoDia(fecha) {
    const date = new Date(`${fecha}T12:00:00`);

    return new Intl.DateTimeFormat(
        "es-CL",
        {
            weekday: "short",
            day: "2-digit",
            month: "2-digit"
        }
    ).format(date);
}


function obtenerClaseEstado(estado) {
    return clasesEstado[estado] ?? "pendiente";
}


function obtenerTextoEstado(estado) {
    return textosEstado[estado] ?? estado;
}


function mostrarToast(mensaje) {
    const toast = $("#toast");

    toast.textContent = mensaje;
    toast.classList.add("show");

    clearTimeout(mostrarToast.temporizador);

    mostrarToast.temporizador = setTimeout(() => {
        toast.classList.remove("show");
    }, 2600);
}


function abrirModal(contenido) {
    $("#modalBody").innerHTML = contenido;

    const modal = $("#modal");

    if (!modal.open) {
        modal.showModal();
    }
}


function cerrarModal() {
    const modal = $("#modal");

    if (modal.open) {
        modal.close();
    }
}


function guardarEstado() {
    const estado = copiar(estadoActual());
    guardadoPendiente = true;
    operacionesPendientes += 1;
    queueMicrotask(() => mostrarConexion("Guardando cambios…"));
    colaGuardado = colaGuardado.then(async () => {
        // Solo se envían los registros nuevos o modificados, nunca toda la base.
        for (const [clave, coleccion] of Object.entries(colecciones)) {
            const anteriores = new Map((estadoConfirmado[clave] || []).map(r => [r.id || r.profesionalId, r]));
            for (const registro of estado[clave]) {
                const id = registro.id || registro.profesionalId;
                const anterior = anteriores.get(id);
                if (anterior && JSON.stringify(anterior) === JSON.stringify(registro)) continue;
                const datos = await solicitarEstado({
                    method: anterior ? "PUT" : "POST",
                    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
                    body: JSON.stringify({ record: registro, version: versiones[clave]?.[id] })
                }, `/api/${coleccion}/${anterior ? encodeURIComponent(id) + "/" : ""}`);
                versiones[clave] ||= {};
                versiones[clave][id] = datos.version;
                // Mantiene las fechas normalizadas que confirmó MongoDB.
                const actual = estadoActual()[clave].find(r => (r.id || r.profesionalId) === id);
                if (actual && JSON.stringify(actual) === JSON.stringify(registro)) Object.assign(actual, datos.record);
                const confirmados = estadoConfirmado[clave] ||= [];
                const indice = confirmados.findIndex(r => (r.id || r.profesionalId) === id);
                if (indice < 0) confirmados.push(datos.record);
                else confirmados[indice] = datos.record;
            }
        }
        operacionesPendientes -= 1;
        guardadoPendiente = operacionesPendientes > 0;
        if (!guardadoPendiente) document.querySelector("#databaseStatus")?.close();
    });
    colaGuardado.catch(error => {
        guardadoPendiente = true;
        mostrarConexion(`${error.message} La operación no se completó. ` +
            "Recarga para consultar los registros que sí alcanzaron a guardarse.", true);
    });
    return colaGuardado;
}

async function cargarEstado() {
    const datos = await solicitarEstado();
    ({ profesionales, empresas, validaciones, servicios,
        solicitudes, agendamientos, pagos, trazabilidad } = datos.state);
    versiones = datos.versions;
    estadoConfirmado = copiar(datos.state);
    csrfToken = datos.csrfToken;
}

function registrarTrazabilidad(tipo, titulo, descripcion) {
    trazabilidad.unshift({
        id: nuevoId(),
        tipo,
        titulo,
        descripcion,
        fecha: new Date().toISOString()
    });
}


async function commit() {
    sincronizarPagos();
    await guardarEstado();
    actualizarResumen();
    renderizarSolicitudes();
    renderizarCalendario();
    renderizarAgendamientos();
    renderizarPagos();
    renderizarTrazabilidad();
    renderizarActividadInicio();
}


function actualizarResumen() {
    const validados = profesionales.filter(
        profesional => profesional.estado === "validado"
    ).length;

    const serviciosDisponibles = servicios.filter(
        servicio => servicio.disponible
    ).length;

    const solicitudesPendientes = solicitudes.filter(
        solicitud => solicitud.estado === "pendiente"
    ).length;

    const validacionesPendientes = validaciones.filter(
        validacion => validacion.estado !== "validado"
    ).length;


    $("#kpiProfesionales").textContent =
        profesionales.length;

    $("#kpiEmpresas").textContent =
        empresas.length;

    $("#kpiServicios").textContent =
        servicios.length;

    $("#kpiSolicitudes").textContent =
        solicitudes.length;

    $("#kpiValidados").textContent =
        `${validados} validados`;

    $("#kpiServiciosDisponibles").textContent =
        `${serviciosDisponibles} disponibles`;

    $("#kpiSolicitudesPendientes").textContent =
        `${solicitudesPendientes} pendientes`;

    $("#badgeSolicitudes").textContent =
        solicitudesPendientes;

    $("#badgeValidaciones").textContent =
        validacionesPendientes;

    $("#heroValidados").textContent =
        validados;

    $("#heroValidadosDetalle").textContent =
        `${validados} de ${profesionales.length} profesionales`;

    $("#professionalCount").textContent =
        profesionales.length;

    $("#companyCount").textContent =
        empresas.length;

    $("#serviceCount").textContent =
        servicios.length;
}


function pintarVista(nombre) {
    $$(".view").forEach(vista => {
        vista.classList.toggle(
            "active",
            vista.id === nombre
        );
    });


    $$(".nav").forEach(boton => {
        const activo = boton.dataset.route === nombre;

        boton.classList.toggle("active", activo);

        if (activo) {
            boton.setAttribute(
                "aria-current",
                "page"
            );
        } else {
            boton.removeAttribute("aria-current");
        }
    });


    $(".sidebar").classList.remove("open");

    $("#menu").setAttribute(
        "aria-expanded",
        "false"
    );
}


function irA(ruta) {
    if (location.hash === `#${ruta}`) {
        enrutar();
        return;
    }

    location.hash = ruta;
}


function enrutar() {
    const ruta =
        location.hash.slice(1) || "inicio";

    const [vista, parametro] =
        ruta.split("/");


    const vistasValidas = [
        "inicio",
        "profesionales",
        "perfil",
        "empresas",
        "validaciones",
        "servicios",
        "solicitudes",
        "calendario",
        "pagos",
        "trazabilidad",
        "terminos",
        "contratos"
    ];


    if (!vistasValidas.includes(vista)) {
        location.hash = "inicio";
        return;
    }


    pintarVista(vista);


    if (vista === "perfil" && parametro) {
        renderizarPerfil(parametro);
    }
}


function renderizarActividadInicio() {
    const contenedor = $("#homeActivity");

    const eventos = [...trazabilidad]
        .sort(
            (a, b) =>
                new Date(b.fecha) -
                new Date(a.fecha)
        )
        .slice(0, 5);


    if (!eventos.length) {
        contenedor.innerHTML = `
            <div class="empty">
                No hay actividad registrada.
            </div>
        `;

        return;
    }


    contenedor.innerHTML = eventos.map(evento => `
        <div class="list-row">
            <div class="dot">•</div>

            <div>
                <strong>
                    ${escaparHTML(evento.titulo)}
                </strong>

                <p>
                    ${escaparHTML(evento.descripcion)}
                </p>

                <small>
                    ${escaparHTML(formatoFecha(evento.fecha))}
                </small>
            </div>
        </div>
    `).join("");
}


function renderizarProfesionales() {
    const texto =
        normalizar($("#professionalSearch").value);

    const filtro =
        $("#professionalFilter").value;


    const resultado = profesionales.filter(
        profesional => {
            const contenido = normalizar(
                `${profesional.nombre}
                 ${profesional.profesion}
                 ${profesional.especialidad}`
            );

            const coincideBusqueda =
                contenido.includes(texto);

            const coincideFiltro =
                filtro === "todos" ||
                profesional.estado === filtro;

            return coincideBusqueda &&
                coincideFiltro;
        }
    );


    const contenedor =
        $("#professionalsGrid");


    if (!resultado.length) {
        contenedor.innerHTML = `
            <article class="panel empty">
                No se encontraron profesionales.
            </article>
        `;

        return;
    }


    contenedor.innerHTML =
        resultado.map(profesional => `
            <article class="professional-card">

                <div class="professional-top">

                    <div class="avatar">
                        ${escaparHTML(profesional.iniciales)}
                    </div>

                    <div class="professional-info">

                        <h3>
                            ${escaparHTML(profesional.nombre)}
                        </h3>

                        <p>
                            ${escaparHTML(profesional.profesion)}
                        </p>

                        <span class="status ${obtenerClaseEstado(profesional.estado)}">
                            ${escaparHTML(profesional.estadoTexto)}
                        </span>

                    </div>

                </div>


                <div class="professional-metrics">

                    <div>
                        <strong>
                            ${profesional.serviciosRealizados}
                        </strong>

                        <span>
                            Servicios
                        </span>
                    </div>

                    <div>
                        <strong>
                            ${escaparHTML(profesional.cumplimiento)}
                        </strong>

                        <span>
                            Cumplimiento
                        </span>
                    </div>

                    <div>
                        <strong>
                            ${profesional.empresas}
                        </strong>

                        <span>
                            Empresas
                        </span>
                    </div>

                </div>


                <div class="card-actions">

                    <button
                        data-action="ver-actividad"
                        data-id="${escaparHTML(profesional.id)}"
                    >
                        Ver actividad
                    </button>

                    <button
                        data-action="ver-perfil"
                        data-id="${escaparHTML(profesional.id)}"
                    >
                        Ver Perfil Skilly
                    </button>

                </div>

            </article>
        `).join("");
}


function renderizarPerfil(id) {
    const profesional =
        obtenerProfesional(id);

    if (!profesional) {
        irA("profesionales");
        return;
    }


    const serviciosProfesional =
        servicios.filter(
            servicio =>
                servicio.profesionalId === id
        );


    const linkedin =
        urlSegura(profesional.linkedin);


    const linkedinHTML = linkedin
        ? `
            <a
                class="outline-action"
                href="${escaparHTML(linkedin)}"
                target="_blank"
                rel="noopener noreferrer"
            >
                Ver LinkedIn
            </a>
        `
        : `
            <button
                class="outline-action"
                data-action="linkedin-no-informado"
            >
                LinkedIn no informado
            </button>
        `;


    const experienciaHTML =
        profesional.experienciaLaboral
            .map(item => `
                <div class="timeline-item">

                    <strong>
                        ${escaparHTML(item.cargo)}
                    </strong>

                    <span>
                        ${escaparHTML(item.empresa)}
                    </span>

                    <span>
                        ${escaparHTML(item.periodo)}
                    </span>

                </div>
            `)
            .join("");


    const educacionHTML =
        profesional.educacion
            .map(item => `
                <div class="timeline-item">

                    <strong>
                        ${escaparHTML(item.titulo)}
                    </strong>

                    <span>
                        ${escaparHTML(item.institucion)}
                    </span>

                    <span>
                        ${escaparHTML(item.periodo)}
                    </span>

                </div>
            `)
            .join("");


    const cursosHTML =
        profesional.cursos.length
            ? profesional.cursos
                .map(curso => `
                    <span class="tag">
                        ${escaparHTML(curso)}
                    </span>
                `)
                .join("")
            : `
                <span class="muted">
                    Sin cursos informados.
                </span>
            `;


    const serviciosHTML =
        serviciosProfesional.length
            ? serviciosProfesional
                .map(servicio => `
                    <div class="timeline-item">

                        <strong>
                            ${escaparHTML(servicio.titulo)}
                        </strong>

                        <span>
                            ${escaparHTML(servicio.descripcion)}
                        </span>

                        <span>
                            ${formatoMoneda(servicio.precio)}
                        </span>

                    </div>
                `)
                .join("")
            : `
                <span class="muted">
                    Sin servicios publicados.
                </span>
            `;


    $("#profileContent").innerHTML = `
        <div class="profile-hero">

            <div class="profile-intro">

                <div class="profile-avatar">
                    ${escaparHTML(profesional.iniciales)}
                </div>

                <div class="profile-copy">

                    <span class="eyebrow">
                        PERFIL SKILLY
                    </span>

                    <h1>
                        ${escaparHTML(profesional.nombre)}
                    </h1>

                    <p>
                        ${escaparHTML(profesional.profesion)}
                    </p>

                    <div class="profile-meta">

                        <span>
                            ${escaparHTML(profesional.ubicacion)}
                        </span>

                        <span>
                            ${escaparHTML(profesional.experiencia)}
                            de experiencia
                        </span>

                        <span class="status ${obtenerClaseEstado(profesional.estado)}">
                            ${escaparHTML(profesional.estadoTexto)}
                        </span>

                    </div>

                </div>

            </div>


            <div class="profile-actions">
                <button class="btn ghost" data-action="ir-validacion" data-id="${escaparHTML(profesional.id)}">Ver recorrido de validación</button>

                <button
                    class="main-action"
                    data-action="servicios-profesional"
                    data-id="${escaparHTML(profesional.id)}"
                >
                    Ver servicios
                </button>

                ${linkedinHTML}

            </div>

        </div>


        <div class="trust-grid">

            <div>
                <span>Servicios realizados</span>
                <strong>${profesional.serviciosRealizados}</strong>
            </div>

            <div>
                <span>Cumplimiento</span>
                <strong>${escaparHTML(profesional.cumplimiento)}</strong>
            </div>

            <div>
                <span>Organizaciones</span>
                <strong>${profesional.empresas}</strong>
            </div>

            <div>
                <span>Experiencia</span>
                <strong>${escaparHTML(profesional.experiencia)}</strong>
            </div>

            <div>
                <span>Estado</span>
                <strong>${escaparHTML(profesional.estadoTexto)}</strong>
            </div>

        </div>


        <div class="profile-layout">

            <div>

                <section class="profile-section">
                    <h2>Acerca del profesional</h2>

                    <p>
                        ${escaparHTML(profesional.resumen)}
                    </p>
                </section>


                <section class="profile-section">
                    <h2>Experiencia laboral</h2>
                    ${experienciaHTML}
                </section>


                <section class="profile-section">
                    <h2>Formación académica</h2>
                    ${educacionHTML}
                </section>

            </div>


            <div>

                <section class="profile-section">

                    <h2>Habilidades</h2>

                    <div class="tag-list">

                        ${profesional.habilidades.map(habilidad => `
                            <span class="tag">
                                ${escaparHTML(habilidad)}
                            </span>
                        `).join("")}

                    </div>

                </section>


                <section class="profile-section">

                    <h2>
                        Cursos y certificaciones
                    </h2>

                    <div class="tag-list">
                        ${cursosHTML}
                    </div>

                </section>


                <section class="profile-section">
                    <h2>Servicios</h2>
                    ${serviciosHTML}
                </section>

            </div>

        </div>
    `;
}


function abrirActividadProfesional(id) {
    const profesional =
        obtenerProfesional(id);

    if (!profesional) {
        return;
    }


    const solicitudesProfesional =
        solicitudes.filter(
            solicitud =>
                solicitud.profesionalId === id
        );

    const agendaProfesional =
        agendamientos.filter(
            agenda =>
                agenda.profesionalId === id
        );


    abrirModal(`
        <span class="eyebrow">
            ACTIVIDAD PROFESIONAL
        </span>

        <h1 id="modalTitle">
            ${escaparHTML(profesional.nombre)}
        </h1>

        <p class="muted">
            Actividad demostrativa registrada dentro de Skilly.
        </p>


        <div class="metric-grid">

            <div class="metric">
                <span>Solicitudes</span>
                <strong>${solicitudesProfesional.length}</strong>
            </div>

            <div class="metric">
                <span>Agendamientos</span>
                <strong>${agendaProfesional.length}</strong>
            </div>

            <div class="metric">
                <span>Histórico</span>
                <strong>${profesional.serviciosRealizados}</strong>
            </div>

        </div>
    `);
}


function renderizarEmpresas() {
    const texto =
        normalizar($("#companySearch").value);

    const filtro =
        $("#companyFilter").value;


    const resultado =
        empresas.filter(empresa => {
            const contenido =
                normalizar(
                    `${empresa.nombre}
                     ${empresa.rubro}
                     ${empresa.contacto}`
                );

            const coincideBusqueda =
                contenido.includes(texto);

            const coincideFiltro =
                filtro === "todas" ||
                empresa.estado === filtro;

            return coincideBusqueda &&
                coincideFiltro;
        });


    const tabla =
        $("#companiesTable");


    if (!resultado.length) {
        tabla.innerHTML = `
            <tr>
                <td colspan="6">
                    No se encontraron empresas.
                </td>
            </tr>
        `;

        return;
    }


    tabla.innerHTML =
        resultado.map(empresa => {
            const cantidadSolicitudes =
                solicitudes.filter(
                    solicitud =>
                        solicitud.empresaId === empresa.id
                ).length;

            return `
                <tr>

                    <td>
                        <strong>
                            ${escaparHTML(empresa.nombre)}
                        </strong>
                    </td>

                    <td>
                        ${escaparHTML(empresa.rubro)}
                    </td>

                    <td>
                        ${escaparHTML(empresa.contacto)}
                    </td>

                    <td>
                        ${cantidadSolicitudes}
                    </td>

                    <td>
                        <span class="status ${obtenerClaseEstado(empresa.estado)}">
                            ${obtenerTextoEstado(empresa.estado)}
                        </span>
                    </td>

                    <td>
                        <button
                            data-action="ver-empresa"
                            data-id="${escaparHTML(empresa.id)}"
                        >
                            Ver empresa
                        </button>
                    </td>

                </tr>
            `;
        }).join("");
}


function abrirEmpresa(id) {
    const empresa =
        obtenerEmpresa(id);

    if (!empresa) {
        return;
    }


    const actividad =
        solicitudes.filter(
            solicitud =>
                solicitud.empresaId === id
        );


    abrirModal(`
        <span class="eyebrow">
            EMPRESA
        </span>

        <h1 id="modalTitle">
            ${escaparHTML(empresa.nombre)}
        </h1>

        <p class="muted">
            ${escaparHTML(empresa.descripcion)}
        </p>


        <div class="modal-section">

            <p>
                <strong>Rubro:</strong>
                ${escaparHTML(empresa.rubro)}
            </p>

            <p>
                <strong>Contacto:</strong>
                ${escaparHTML(empresa.contacto)}
            </p>

            <p>
                <strong>Correo:</strong>
                ${escaparHTML(empresa.correo)}
            </p>

            <p>
                <strong>Miembro desde:</strong>
                ${escaparHTML(empresa.miembroDesde)}
            </p>

            <p>
                <strong>Estado:</strong>
                ${obtenerTextoEstado(empresa.estado)}
            </p>

        </div>


        <div class="modal-section">

            <strong>
                Solicitudes registradas
            </strong>

            ${
                actividad.length
                    ? actividad.map(solicitud => {
                        const servicio =
                            obtenerServicio(
                                solicitud.servicioId
                            );

                        return `
                            <p>
                                ${escaparHTML(servicio.titulo)}
                                ·
                                ${obtenerTextoEstado(solicitud.estado)}
                            </p>
                        `;
                    }).join("")
                    : `
                        <p>
                            Sin solicitudes registradas.
                        </p>
                    `
            }

        </div>
    `);
}


function renderizarServicios() {
    const texto =
        normalizar($("#serviceSearch").value);

    const filtro =
        $("#serviceFilter").value;


    const resultado =
        servicios.filter(servicio => {
            const profesional =
                obtenerProfesional(
                    servicio.profesionalId
                );

            const contenido =
                normalizar(
                    `${servicio.titulo}
                     ${servicio.categoria}
                     ${profesional.nombre}`
                );

            const coincideBusqueda =
                contenido.includes(texto);

            const coincideFiltro =
                filtro === "todos" ||
                servicio.categoria === filtro;

            return coincideBusqueda &&
                coincideFiltro;
        });


    const contenedor =
        $("#servicesGrid");


    if (!resultado.length) {
        contenedor.innerHTML = `
            <article class="panel empty">
                No se encontraron servicios.
            </article>
        `;

        return;
    }


    contenedor.innerHTML =
        resultado.map(servicio => {
            const profesional =
                obtenerProfesional(
                    servicio.profesionalId
                );

            return `
                <article class="service-card">

                    <span class="category">
                        ${escaparHTML(servicio.categoria)}
                    </span>

                    <h3>
                        ${escaparHTML(servicio.titulo)}
                    </h3>

                    <p>
                        ${escaparHTML(servicio.descripcion)}
                    </p>


                    <div class="service-provider">

                        <div class="avatar">
                            ${escaparHTML(profesional.iniciales)}
                        </div>

                        <div>
                            <strong>
                                ${escaparHTML(profesional.nombre)}
                            </strong>

                            <span>
                                ${escaparHTML(profesional.estadoTexto)}
                            </span>
                        </div>

                    </div>


                    <div class="service-info">

                        <span>
                            ${escaparHTML(servicio.duracion)}
                        </span>

                        <span>
                            ${
                                servicio.disponible
                                    ? "Publicado"
                                    : "No habilitado"
                            }
                        </span>

                    </div>


                    <div class="service-footer">

                        <div>
                            <small>
                                Valor demostrativo
                            </small>

                            <strong>
                                ${formatoMoneda(servicio.precio)}
                            </strong>
                        </div>

                        <button
                            class="btn primary"
                            data-action="ver-servicio"
                            data-id="${escaparHTML(servicio.id)}"
                        >
                            Ver servicio
                        </button>

                    </div>

                </article>
            `;
        }).join("");
}


function abrirServicio(id) {
    const servicio =
        obtenerServicio(id);

    if (!servicio) {
        return;
    }

    const profesional =
        obtenerProfesional(
            servicio.profesionalId
        );


    abrirModal(`
        <span class="eyebrow">
            SERVICIO
        </span>

        <h1 id="modalTitle">
            ${escaparHTML(servicio.titulo)}
        </h1>

        <p class="muted">
            ${escaparHTML(servicio.descripcion)}
        </p>


        <div class="modal-section">

            <strong>
                Profesional
            </strong>

            <p>
                ${escaparHTML(profesional.nombre)}
            </p>

            <p>
                ${escaparHTML(profesional.profesion)}
            </p>

            <span class="status ${obtenerClaseEstado(profesional.estado)}">
                ${escaparHTML(profesional.estadoTexto)}
            </span>

        </div>


        <div class="modal-section">

            <p>
                <strong>Categoría:</strong>
                ${escaparHTML(servicio.categoria)}
            </p>

            <p>
                <strong>Duración referencial:</strong>
                ${escaparHTML(servicio.duracion)}
            </p>

            <p>
                <strong>Valor demostrativo:</strong>
                ${formatoMoneda(servicio.precio)}
            </p>

        </div>


        <h2>Revisión automática de publicación</h2>
        ${comprobacionesHTML(servicio.revision)}
        <div class="modal-actions">
            <button class="btn ghost" data-action="editar-servicio" data-id="${escaparHTML(id)}">Corregir servicio</button>
            <button class="btn ghost" data-action="revisar-servicio" data-id="${escaparHTML(id)}">Volver a revisar</button>
            <button class="btn ghost" data-action="historial-servicio" data-id="${escaparHTML(id)}">Historial de revisiones</button>

            <button
                class="btn ghost"
                data-action="ver-perfil"
                data-id="${escaparHTML(profesional.id)}"
            >
                Ver Perfil Skilly
            </button>

            ${
                servicio.disponible
                    ? `
                        <button
                            class="btn primary"
                            data-action="solicitar-servicio"
                            data-id="${escaparHTML(servicio.id)}"
                        >
                            Enviar solicitud
                        </button>
                    `
                    : `
                        <button
                            class="btn primary"
                            disabled
                        >
                            Pendiente de requisitos de publicación
                        </button>
                    `
            }

        </div>
    `);
}


function renderizarSolicitudes() {
    const tabla =
        $("#requestsTable");


    if (!solicitudes.length) {
        tabla.innerHTML = `
            <tr>
                <td colspan="6">
                    No hay solicitudes.
                </td>
            </tr>
        `;

        return;
    }


    tabla.innerHTML =
        [...solicitudes]
            .sort(
                (a, b) =>
                    new Date(b.fecha) -
                    new Date(a.fecha)
            )
            .map(solicitud => {
                const empresa =
                    obtenerEmpresa(
                        solicitud.empresaId
                    );

                const profesional =
                    obtenerProfesional(
                        solicitud.profesionalId
                    );

                const servicio =
                    obtenerServicio(
                        solicitud.servicioId
                    );

                return `
                    <tr>

                        <td>
                            <strong>
                                ${escaparHTML(empresa.nombre)}
                            </strong>
                        </td>

                        <td>
                            ${escaparHTML(servicio.titulo)}
                        </td>

                        <td>
                            ${escaparHTML(profesional.nombre)}
                        </td>

                        <td>
                            ${escaparHTML(formatoFecha(solicitud.fecha))}
                        </td>

                        <td>
                            <span class="status ${obtenerClaseEstado(solicitud.estado)}">
                                ${obtenerTextoEstado(solicitud.estado)}
                            </span>
                        </td>

                        <td>
                            <button
                                data-action="ver-solicitud"
                                data-id="${escaparHTML(solicitud.id)}"
                            >
                                Ver solicitud
                            </button>
                        </td>

                    </tr>
                `;
            }).join("");
}


function abrirSolicitud(id) {
    const solicitud =
        obtenerSolicitud(id);

    if (!solicitud) {
        return;
    }


    const empresa =
        obtenerEmpresa(
            solicitud.empresaId
        );

    const profesional =
        obtenerProfesional(
            solicitud.profesionalId
        );

    const servicio =
        obtenerServicio(
            solicitud.servicioId
        );


    const simulacion =
        solicitud.estado === "pendiente"
            ? `
                <div class="modal-section">

                    <strong>
                        Simular respuesta del profesional
                    </strong>

                    <p>
                        Estos controles representan una respuesta
                        realizada por el profesional, no por el
                        administrador de Skilly.
                    </p>

                    <div class="modal-actions">

                        <button
                            class="btn primary"
                            data-action="responder-solicitud"
                            data-id="${escaparHTML(solicitud.id)}"
                            data-estado="aceptada"
                        >
                            Simular aceptación
                        </button>

                        <button
                            class="btn ghost"
                            data-action="responder-solicitud"
                            data-id="${escaparHTML(solicitud.id)}"
                            data-estado="rechazada"
                        >
                            Simular rechazo
                        </button>

                    </div>

                </div>
            `
            : "";


    abrirModal(`
        <span class="eyebrow">
            SOLICITUD
        </span>

        <h1 id="modalTitle">
            ${escaparHTML(servicio.titulo)}
        </h1>


        <div class="modal-section">

            <p>
                <strong>Empresa:</strong>
                ${escaparHTML(empresa.nombre)}
            </p>

            <p>
                <strong>Profesional:</strong>
                ${escaparHTML(profesional.nombre)}
            </p>

            <p>
                <strong>Enviada:</strong>
                ${escaparHTML(formatoFecha(solicitud.fecha))}
            </p>

            <p>
                <strong>Expira:</strong>
                ${escaparHTML(formatoFecha(solicitud.expiracion))}
            </p>

            <p>
                <strong>Estado:</strong>
                ${obtenerTextoEstado(solicitud.estado)}
            </p>

        </div>


        <div class="notice">
            Skilly realiza el seguimiento de esta solicitud.
            La decisión de aceptar o rechazar corresponde
            exclusivamente al profesional solicitado.
        </div>

        ${simulacion}


        ${
            solicitud.estado === "aceptada"
                ? `
                    <button
                        class="btn primary"
                        data-route="calendario"
                    >
                        Ir al calendario
                    </button>
                `
                : ""
        }
    `);
}


async function responderSolicitud(id, nuevoEstado) {
    const solicitud =
        obtenerSolicitud(id);

    if (!solicitud) {
        return;
    }


    const permitidas =
        transicionesSolicitud[
            solicitud.estado
        ] ?? [];


    if (!permitidas.includes(nuevoEstado)) {
        mostrarToast(
            "Ese cambio de estado no está permitido."
        );

        return;
    }


    solicitud.estado =
        nuevoEstado;


    const profesional =
        obtenerProfesional(
            solicitud.profesionalId
        );


    registrarTrazabilidad(
        "Solicitud",
        `Solicitud ${obtenerTextoEstado(nuevoEstado).toLowerCase()}`,
        `${profesional.nombre} registró una respuesta a la solicitud.`
    );


    cerrarModal();
    try {
        await commit();
    } catch (error) {
        mostrarToast(error.message);
        return;
    }


    mostrarToast(
        `Solicitud ${obtenerTextoEstado(nuevoEstado).toLowerCase()}.`
    );
}


function abrirNuevaSolicitud(servicioId = "") {
    cerrarModal();


    const disponibles =
        servicios.filter(
            servicio => servicio.disponible
        );


    abrirModal(`
        <span class="eyebrow">
            NUEVA SOLICITUD
        </span>

        <h1 id="modalTitle">
            Crear solicitud
        </h1>


        <form
            id="requestForm"
            class="form"
        >

            <label>
                Empresa

                <select
                    id="requestCompany"
                    required
                >
                    ${empresas
                        .filter(
                            empresa =>
                                empresa.estado === "activa"
                        )
                        .map(empresa => `
                            <option value="${escaparHTML(empresa.id)}">
                                ${escaparHTML(empresa.nombre)}
                            </option>
                        `)
                        .join("")}
                </select>
            </label>


            <label>
                Servicio

                <select
                    id="requestService"
                    required
                >
                    ${disponibles.map(servicio => `
                        <option
                            value="${escaparHTML(servicio.id)}"
                            ${
                                servicio.id === servicioId
                                    ? "selected"
                                    : ""
                            }
                        >
                            ${escaparHTML(servicio.titulo)}
                        </option>
                    `).join("")}
                </select>
            </label>


            <label>
                Fecha y hora de envío

                <input
                    id="requestDate"
                    type="datetime-local"
                    required
                >
            </label>


            <button
                class="btn primary"
                type="submit"
            >
                Registrar solicitud
            </button>

        </form>
    `);


    $("#requestForm").addEventListener(
        "submit",
        guardarSolicitud
    );
}


async function guardarSolicitud(evento) {
    evento.preventDefault();


    const empresaId =
        $("#requestCompany").value;

    const servicioId =
        $("#requestService").value;

    const fecha =
        $("#requestDate").value;

    const servicio =
        obtenerServicio(servicioId);


    if (!servicio || !servicio.disponible) {
        mostrarToast(
            "El servicio no está disponible."
        );

        return;
    }


    const fechaSolicitud =
        new Date(fecha);


    if (
        Number.isNaN(fechaSolicitud.getTime()) ||
        fechaSolicitud <= new Date()
    ) {
        mostrarToast(
            "La fecha debe ser futura."
        );

        return;
    }


    const expiracion =
        new Date(
            fechaSolicitud.getTime() +
            48 * 60 * 60 * 1000
        );


    solicitudes.unshift({
        id: nuevoId(),
        empresaId,
        servicioId,
        profesionalId:
            servicio.profesionalId,
        fecha:
            fechaSolicitud.toISOString(),
        expiracion:
            expiracion.toISOString(),
        estado: "pendiente"
    });


    registrarTrazabilidad(
        "Solicitud",
        "Nueva solicitud registrada",
        `Se registró una solicitud para ${servicio.titulo}.`
    );


    cerrarModal();
    try {
        await commit();
    } catch (error) {
        mostrarToast(error.message);
        return;
    }


    mostrarToast(
        "Solicitud registrada."
    );
}


function slotOcupado(
    profesionalId,
    fecha
) {
    return agendamientos.some(
        agenda =>
            agenda.profesionalId === profesionalId &&
            new Date(agenda.fecha).getTime() === new Date(fecha).getTime() &&
            agenda.estado !== "cancelado"
    );
}


function seleccionarHorario(
    profesionalId,
    fecha
) {
    const profesional =
        obtenerProfesional(
            profesionalId
        );


    if (
        slotOcupado(
            profesionalId,
            fecha
        )
    ) {
        mostrarToast(
            "Ese horario ya está ocupado."
        );

        renderizarCalendario();

        return;
    }


    const aceptadas =
        solicitudes.filter(
            solicitud =>
                solicitud.profesionalId === profesionalId &&
                solicitud.estado === "aceptada" &&
                !agendamientos.some(
                    agenda =>
                        agenda.solicitudId === solicitud.id
                )
        );


    if (!aceptadas.length) {
        abrirModal(`
            <span class="eyebrow">
                CALENDARIO
            </span>

            <h1 id="modalTitle">
                Horario disponible
            </h1>

            <div class="notice">
                ${escaparHTML(profesional.nombre)}
                no tiene actualmente una solicitud aceptada
                pendiente de agendamiento.
            </div>
        `);

        return;
    }


    abrirModal(`
        <span class="eyebrow">
            AGENDAMIENTO
        </span>

        <h1 id="modalTitle">
            ${escaparHTML(formatoFecha(fecha))}
        </h1>

        <p class="muted">
            ${escaparHTML(profesional.nombre)}
        </p>


        <form
            id="appointmentForm"
            class="form"
        >

            <label>
                Solicitud aceptada

                <select
                    id="appointmentRequest"
                    required
                >
                    ${aceptadas.map(solicitud => {
                        const empresa =
                            obtenerEmpresa(
                                solicitud.empresaId
                            );

                        const servicio =
                            obtenerServicio(
                                solicitud.servicioId
                            );

                        return `
                            <option value="${escaparHTML(solicitud.id)}">
                                ${escaparHTML(empresa.nombre)}
                                -
                                ${escaparHTML(servicio.titulo)}
                            </option>
                        `;
                    }).join("")}
                </select>
            </label>


            <button
                class="btn primary"
                type="submit"
            >
                Registrar horario
            </button>

        </form>


        <div class="notice">
            Para este prototipo el horario queda registrado
            como propuesto. La regla definitiva de confirmación
            debe ser validada con Skilly.
        </div>
    `);


    $("#appointmentForm").addEventListener(
        "submit",
        async evento => {
            evento.preventDefault();

            await guardarAgendamiento(
                profesionalId,
                fecha
            );
        }
    );
}


function guardarAgendamiento(profesionalId, fecha) {
    const form=$("#appointmentForm");
    form.dataset.operationKey ||= nuevoId();
    return ejecutarWorkflow("/api/operaciones/",{headers:{"Content-Type":"application/json"},body:JSON.stringify({accion:"agendar",solicitudId:$("#appointmentRequest").value,fecha:new Date(fecha).toISOString(),claveOperacion:form.dataset.operationKey})});
}

function renderizarPagos() {
    const tabla =
        $("#paymentsTable");


    if (!pagos.length) {
        tabla.innerHTML = `
            <tr>
                <td colspan="7">
                    Todavía no existen pagos registrados.
                </td>
            </tr>
        `;
    } else {
        tabla.innerHTML =
            [...pagos]
                .sort(
                    (a, b) =>
                        new Date(b.fecha) -
                        new Date(a.fecha)
                )
                .map(pago => {
                    const empresa =
                        obtenerEmpresa(
                            pago.empresaId
                        );

                    const profesional =
                        obtenerProfesional(
                            pago.profesionalId
                        );

                    const servicio =
                        obtenerServicio(
                            pago.servicioId
                        );

                    return `
                        <tr>

                            <td>
                                ${escaparHTML(empresa.nombre)}
                            </td>

                            <td>
                                ${escaparHTML(profesional.nombre)}
                            </td>

                            <td>
                                ${escaparHTML(servicio.titulo)}
                            </td>

                            <td>
                                ${formatoMoneda(pago.monto)}
                            </td>

                            <td>
                                ${escaparHTML(formatoFecha(pago.fecha))}
                            </td>

                            <td>
                                <span class="status ${obtenerClaseEstado(pago.estado)}">
                                    ${obtenerTextoEstado(pago.estado)}
                                </span>
                            </td>

                            <td>
                                <button
                                    data-action="ver-pago"
                                    data-id="${escaparHTML(pago.id)}"
                                >
                                    Ver pago
                                </button>
                            </td>

                        </tr>
                    `;
                }).join("");
    }


    const pendientes =
        pagos.filter(
            pago =>
                pago.estado === "pendiente"
        ).length;

    const completados =
        pagos.filter(
            pago =>
                ["pagado", "finalizado"].includes(pago.estado)
        ).length;

    const volumen =
        pagos.reduce(
            (total, pago) =>
                total + pago.monto,
            0
        );


    $("#paymentsTotal").textContent =
        pagos.length;

    $("#paymentsPending").textContent =
        pendientes;

    $("#paymentsCompleted").textContent =
        completados;

    $("#paymentsVolume").textContent =
        formatoMoneda(volumen);
}


function abrirNuevoPago() {
    abrirModal(`<h1 id="modalTitle">Seguimiento de servicios</h1>
        <p>Los pagos se generan desde cada agendamiento. Marca el servicio como realizado en Calendario para habilitar su pago.</p>
        <button class="btn primary" id="goCalendar">Ir al calendario</button>`);
    $("#goCalendar").onclick = () => { cerrarModal(); irA("calendario"); };
}

// Cada agendamiento tiene un único seguimiento económico; no se crean pagos aislados.
function sincronizarPagos() { /* El seguimiento económico se calcula en el servidor. */ }

function operarAgenda(id,accion,detalle=null) {
    const agenda=agendamientos.find(a=>a.id===id);
    if(!agenda)return;
    return ejecutarWorkflow("/api/operaciones/",{headers:{"Content-Type":"application/json"},body:JSON.stringify({agendaId:id,version:versiones.agendamientos[id],accion,evaluacion:detalle})});
}
function avanzarServicio(id) { const agenda=agendamientos.find(a=>a.id===id);return operarAgenda(id,agenda?.estado==="propuesto"?"confirmar":"realizar"); }
function procesarPago(id) { const pago=pagos.find(p=>p.id===id);if(pago)return operarAgenda(pago.agendaId,"pagar"); }
function finalizarServicio(id) { const pago=pagos.find(p=>p.id===id);if(pago)return operarAgenda(pago.agendaId,"finalizar"); }

function abrirEvaluacion(id) {
    const pago = pagos.find(p => p.id === id);
    if (!pago || pago.estado !== "finalizado" || pago.evaluacion) return;
    abrirModal(`<h1 id="modalTitle">Evaluación de la empresa · simulación</h1>
        <form id="reviewForm" class="form">
        <label>Calificación<select id="reviewScore" required>
        <option value="">Seleccionar</option>${[5,4,3,2,1].map(n => `<option value="${n}">${n} de 5</option>`).join("")}</select></label>
        <label>Comentario<textarea id="reviewComment" maxlength="1000" required></textarea></label>
        <button class="btn primary">Guardar evaluación</button></form>`);
    $("#reviewForm").onsubmit = async e => {
        e.preventDefault();
        const nota = Number($("#reviewScore").value), comentario = $("#reviewComment").value.trim();
        if (pago.evaluacion || pago.estado !== "finalizado" || !Number.isInteger(nota) || nota < 1 || nota > 5 || !comentario) return;
        await operarAgenda(pago.agendaId,"evaluar",{nota,comentario});
    };
}

function abrirPago(id) {
    const pago =
        pagos.find(
            item =>
                item.id === id
        );


    if (!pago) {
        return;
    }


    const empresa =
        obtenerEmpresa(
            pago.empresaId
        );

    const profesional =
        obtenerProfesional(
            pago.profesionalId
        );

    const servicio =
        obtenerServicio(
            pago.servicioId
        );


    abrirModal(`
        <span class="eyebrow">
            PAGO
        </span>

        <h1 id="modalTitle">
            ${formatoMoneda(pago.monto)}
        </h1>


        <div class="modal-section">

            <p>
                <strong>Empresa:</strong>
                ${escaparHTML(empresa.nombre)}
            </p>

            <p>
                <strong>Profesional:</strong>
                ${escaparHTML(profesional.nombre)}
            </p>

            <p>
                <strong>Servicio:</strong>
                ${escaparHTML(servicio.titulo)}
            </p>

            <p>
                <strong>Fecha:</strong>
                ${escaparHTML(formatoFecha(pago.fecha))}
            </p>

            <p>
                <strong>Estado:</strong>
                ${obtenerTextoEstado(pago.estado)}
            </p>

        </div>


        <div class="modal-section">
            <h2>Avance del servicio</h2>
            <p>${pago.estado === "espera" ? "Pago en espera: confirma y registra la realización del servicio desde Calendario." : "El servicio fue realizado. El monto proviene del servicio contratado."}</p>
            ${pago.estado === "pendiente" ? `<button class="btn primary" data-action="procesar-pago" data-id="${escaparHTML(id)}">Simular pago procesado</button>` : ""}
            ${pago.estado === "pagado" ? `<button class="btn primary" data-action="finalizar-servicio" data-id="${escaparHTML(id)}">Finalizar servicio</button>` : ""}
            <h2>Documentación</h2>
            <p>Responsable y emisión de boleta pendientes de validación con Skilly.</p>
            <label>Referencia de documento (opcional)<input id="documentReference" maxlength="160" value="${escaparHTML(pago.documento || "")}"></label>
            <button class="btn" id="saveDocument">Guardar referencia</button>
            ${pago.evaluacion ? `<h2>Evaluación de la empresa</h2><p>${pago.evaluacion.nota}/5 · ${escaparHTML(pago.evaluacion.comentario)}</p>` : pago.estado === "finalizado" ? `<button class="btn" data-action="evaluar-servicio" data-id="${escaparHTML(id)}">Simular evaluación de la empresa</button>` : ""}
        </div>
        <div class="notice">
            Este registro es demostrativo.
            No representa una transferencia bancaria real.
        </div>
    `);
    $("#saveDocument").onclick = () => operarAgenda(pago.agendaId,"referencia",{referencia:$("#documentReference").value.trim()});
}


function renderizarTrazabilidad() {
    const filtro =
        $("#traceFilter").value;


    const resultado =
        [...trazabilidad]
            .filter(
                evento =>
                    filtro === "todos" ||
                    evento.tipo === filtro
            )
            .sort(
                (a, b) =>
                    new Date(b.fecha) -
                    new Date(a.fecha)
            );


    const contenedor =
        $("#traceList");


    if (!resultado.length) {
        contenedor.innerHTML = `
            <div class="panel empty">
                No hay actividad para este filtro.
            </div>
        `;

        return;
    }


    contenedor.innerHTML =
        resultado.map(evento => `
            <article class="trace-item">

                <span>
                    ${escaparHTML(evento.tipo)}
                </span>

                <h3>
                    ${escaparHTML(evento.titulo)}
                </h3>

                <p>
                    ${escaparHTML(evento.descripcion)}
                </p>

                <small>
                    ${escaparHTML(formatoFecha(evento.fecha))}
                </small>

            </article>
        `).join("");
}


async function manejarAccion(elemento) {
    const accion =
        elemento.dataset.action;

    const id =
        elemento.dataset.id;


    const acciones = {
        "ir-validacion": () => { cerrarModal(); irA("validaciones"); mostrarValidacion(id); },
        "ver-perfil": () => {
            cerrarModal();
            irA(`perfil/${id}`);
        },

        "ver-actividad": () =>
            abrirActividadProfesional(id),

        "ver-empresa": () =>
            abrirEmpresa(id),

        "ver-validacion": () =>
            mostrarValidacion(id),

        "editar-profesional": () => editarProfesional(id || null),
        "subir-documentos": () => subirDocumentos(id),
        "registrar-entrevista": () => registrarEntrevista(id),
        "revisar-profesional": () => ejecutarWorkflow(`/api/profesionales/${encodeURIComponent(id)}/revision/`, {}, () => mostrarValidacion(id)),
        "historial-profesional": () => verHistorialRevision("profesionales", id),
        "editar-servicio": () => editarServicio(id || null),
        "historial-servicio": () => verHistorialRevision("servicios", id),
        "revisar-servicio": () => ejecutarWorkflow(`/api/servicios/${encodeURIComponent(id)}/revision/`, {}, () => abrirServicio(id)),

        "ver-servicio": () =>
            abrirServicio(id),

        "solicitar-servicio": () =>
            abrirNuevaSolicitud(id),

        "ver-solicitud": () =>
            abrirSolicitud(id),

        "responder-solicitud": () =>
            responderSolicitud(
                id,
                elemento.dataset.estado
            ),

        "seleccionar-horario": () =>
            seleccionarHorario(
                elemento.dataset.profesional,
                elemento.dataset.fecha
            ),

        "avanzar-servicio": () => avanzarServicio(id),
        "procesar-pago": () => procesarPago(id),
        "finalizar-servicio": () => finalizarServicio(id),
        "evaluar-servicio": () => abrirEvaluacion(id),
        "ver-pago": () =>
            abrirPago(id),

        "servicios-profesional": () => {
            const profesional =
                obtenerProfesional(id);

            $("#serviceSearch").value =
                profesional.nombre;

            renderizarServicios();

            irA("servicios");
        },

        "linkedin-no-informado": () =>
            mostrarToast(
                "LinkedIn no informado por este profesional."
            )
    };


    try {
        await acciones[accion]?.();
    } catch (error) {
        mostrarToast(error.message || "No se pudo completar la operación.");
    }
}


function conectarEventos() {
    document.addEventListener(
        "click",
        async evento => {
            const ruta =
                evento.target.closest(
                    "[data-route]"
                );

            if (ruta) {
                cerrarModal();

                irA(
                    ruta.dataset.route
                );

                return;
            }


            const accion =
                evento.target.closest(
                    "[data-action]"
                );

            if (accion) {
                await manejarAccion(
                    accion
                );
            }
        }
    );


    $("#modal").addEventListener(
        "click",
        evento => {
            if (
                evento.target ===
                $("#modal")
            ) {
                cerrarModal();
            }
        }
    );


    $("[data-close]").addEventListener(
        "click",
        cerrarModal
    );


    $("#menu").addEventListener(
        "click",
        () => {
            const sidebar =
                $(".sidebar");

            const abierto =
                sidebar.classList.toggle(
                    "open"
                );

            $("#menu").setAttribute(
                "aria-expanded",
                String(abierto)
            );
        }
    );


    $("#professionalSearch")
        .addEventListener(
            "input",
            debounce(
                renderizarProfesionales
            )
        );


    $("#professionalFilter")
        .addEventListener(
            "change",
            renderizarProfesionales
        );


    $("#companySearch")
        .addEventListener(
            "input",
            debounce(
                renderizarEmpresas
            )
        );


    $("#companyFilter")
        .addEventListener(
            "change",
            renderizarEmpresas
        );


    $("#serviceSearch")
        .addEventListener(
            "input",
            debounce(
                renderizarServicios
            )
        );


    $("#serviceFilter")
        .addEventListener(
            "change",
            renderizarServicios
        );


    $("#calendarProfessional")
        .addEventListener(
            "change",
            renderizarCalendario
        );


    $("#traceFilter")
        .addEventListener(
            "change",
            renderizarTrazabilidad
        );


    $("#newRequestButton")
        .addEventListener(
            "click",
            () =>
                abrirNuevaSolicitud()
        );


    $("#newPaymentButton")
        .addEventListener(
            "click",
            abrirNuevoPago
        );


    $("#backProfessionals")
        .addEventListener(
            "click",
            () =>
                irA("profesionales")
        );


    window.addEventListener(
        "hashchange",
        enrutar
    );
}


async function iniciarAplicacion() {
    if (location.protocol === "file:") {
        mostrarConexion("El diseño está disponible, pero los datos requieren el servidor. En la carpeta del proyecto ejecuta .venv/bin/python backend/manage.py runserver y entra a http://127.0.0.1:8000/ para iniciar sesión.");
        const enlace = document.createElement("a");
        enlace.className = "btn primary";
        enlace.href = "http://127.0.0.1:8000/panel/";
        enlace.textContent = "Abrir Skilly en el servidor";
        document.querySelector("#databaseStatus").append(enlace);
        return;
    }
    mostrarConexion("Cargando datos…");
    try {
        await cargarEstado();
        const session=await solicitarEstado({},"/api/auth/sesion/");
        if(session.user) $("#adminDisplayName").textContent=session.user.nombre;
        await solicitarEstado({method: "POST", headers: {"X-CSRFToken": csrfToken}}, "/api/revisiones/");
        await cargarEstado();
        const pagosAnteriores = JSON.stringify(pagos);
        sincronizarPagos();
        if (JSON.stringify(pagos) !== pagosAnteriores) await guardarEstado();
        document.querySelector("#databaseStatus")?.close();
    } catch (error) {
        mostrarConexion(`${error.message} Abre Skilly desde el servidor Django en http://127.0.0.1:8000/.`, true);
        return;
    }

    llenarProfesionalesCalendario();

    conectarEventos();

    actualizarResumen();

    renderizarProfesionales();

    renderizarEmpresas();

    renderizarValidaciones();

    renderizarServicios();

    renderizarSolicitudes();

    renderizarCalendario();

    renderizarAgendamientos();

    renderizarPagos();

    renderizarTrazabilidad();

    renderizarActividadInicio();

    enrutar();
}


document.addEventListener(
    "DOMContentLoaded",
    iniciarAplicacion
);

window.addEventListener("beforeunload", evento => {
    if (guardadoPendiente) {
        evento.preventDefault();
        evento.returnValue = "";
    }
});
