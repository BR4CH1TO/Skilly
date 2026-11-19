/* Calendario mensual: siempre visible, alimentado por MongoDB. */
const calendarZone='America/Santiago';
const calendarState={month:null,day:null};
function fechaCalendario(value) {
    const date=new Date(value);if(!Number.isFinite(date.getTime()))return null;
    return new Intl.DateTimeFormat('en-CA',{timeZone:calendarZone,year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}
function horaCalendario(value) {return new Intl.DateTimeFormat('es-CL',{timeZone:calendarZone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));}
function partesDia(date) {return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;}
function diasDelMes(month) {
    const [year,m]=month.split('-').map(Number),first=new Date(year,m-1,1),start=new Date(year,m-1,1-(first.getDay()+6)%7);
    return Array.from({length:42},(_,i)=>{const date=new Date(start);date.setDate(start.getDate()+i);return partesDia(date);});
}
function profesionalesCalendario() {const id=document.querySelector('#calendarProfessional')?.value;return id&&id!=='todos'?profesionales.filter(p=>p.id===id):profesionales;}
function eventosCalendario() {
    const selected=new Set(profesionalesCalendario().map(p=>p.id));
    const appointments=agendamientos.filter(a=>selected.has(a.profesionalId)&&fechaCalendario(a.fecha));
    const slots=profesionalesCalendario().flatMap(p=>(p.disponibilidad||[]).filter(s=>Number.isFinite(new Date(s).getTime())&&new Date(s)>new Date()).map(s=>({fecha:s,profesionalId:p.id,nombre:p.nombre,habilitado:p.estado==='validado',ocupado:slotOcupado(p.id,s)})));
    return {appointments,slots};
}
function llenarProfesionalesCalendario() {
    const select=document.querySelector('#calendarProfessional');if(!select)return;
    const previous=select.value||'todos';
    select.innerHTML='<option value="todos">Todos los profesionales</option>'+profesionales.map(p=>`<option value="${escaparHTML(p.id)}">${escaparHTML(p.nombre)}${p.estado==='validado'?'':' · '+escaparHTML(obtenerTextoEstado(p.estado))}</option>`).join('');
    select.value=previous==='todos'||profesionales.some(p=>p.id===previous)?previous:'todos';
}
function renderizarCalendario() {
    const today=fechaCalendario(new Date());calendarState.day ||= today;calendarState.month ||= calendarState.day.slice(0,7);
    const {appointments,slots}=eventosCalendario();
    const available=slots.filter(s=>s.habilitado&&!s.ocupado);
    const future=appointments.filter(a=>new Date(a.fecha)>new Date()&&a.estado!=='cancelado');
    const old=appointments.filter(a=>new Date(a.fecha)<=new Date()).sort((a,b)=>new Date(b.fecha)-new Date(a.fecha));
    const activity=[...available,...future].sort((a,b)=>new Date(a.fecha)-new Date(b.fecha))[0];
    document.querySelector('#calendarMonth').value=calendarState.month;
    const [year,month]=calendarState.month.split('-').map(Number);
    document.querySelector('#calendarMonthTitle').textContent=new Intl.DateTimeFormat('es-CL',{month:'long',year:'numeric'}).format(new Date(year,month-1,1));
    document.querySelector('#calendarStats').innerHTML=`<span><strong>${available.length}</strong> horarios futuros libres</span><span><strong>${future.length}</strong> agendamientos futuros</span><span><strong>${old.length}</strong> en el historial</span>`;
    const message=document.querySelector('#calendarStatus');
    if(!profesionales.length)message.textContent='Todavía no hay profesionales registrados. El calendario está disponible; añade un perfil para publicar horarios.';
    else if(!available.length&&!future.length)message.textContent=`No hay horarios futuros publicados ni nuevas reservas para esta selección.${old.length?' Hay agendamientos anteriores: puedes consultarlos con «Ver historial».':''} Usa «Gestionar horarios» para añadir disponibilidad real.`;
    else message.textContent='Selecciona un día para ver sus horarios y reservas. Los horarios se muestran en la zona de Santiago de Chile.';
    const historical=document.querySelector('#calendarHistory');historical.disabled=!old.length;historical.dataset.day=old[0]?fechaCalendario(old[0].fecha):'';
    const next=document.querySelector('#calendarNextActivity');next.disabled=!activity;next.dataset.day=activity?fechaCalendario(activity.fecha):'';
    const grid=document.querySelector('#calendarGrid');grid.classList.add('calendar-month-grid');grid.style.gridTemplateColumns='repeat(7,minmax(0,1fr))';
    grid.innerHTML=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'].map(d=>`<span class="calendar-weekday" aria-hidden="true">${d}</span>`).join('')+diasDelMes(calendarState.month).map(day=>{
        const dayAppointments=appointments.filter(a=>fechaCalendario(a.fecha)===day&&a.estado!=='cancelado');
        const free=available.filter(s=>fechaCalendario(s.fecha)===day);
        const labels=[`${dayAppointments.length} agendamientos`,`${free.length} horarios libres`];
        return `<button type="button" class="calendar-date ${day.slice(0,7)!==calendarState.month?'outside-month':''} ${day===calendarState.day?'selected':''} ${day===today?'today':''}" data-calendar-day="${day}" aria-pressed="${day===calendarState.day}" aria-label="${day}: ${labels.join(', ')}"><span class="calendar-date-number">${Number(day.slice(-2))}</span>${day===today?'<small class="calendar-today-label">Hoy</small>':''}<span class="calendar-day-markers">${dayAppointments.length?`<span class="marker-reserved">${dayAppointments.length}<span> reserva${dayAppointments.length===1?'':'s'}</span></span>`:''}${free.length?`<span class="marker-available">${free.length}<span> libre${free.length===1?'':'s'}</span></span>`:''}</span></button>`;
    }).join('');
    renderizarAgendamientos();
}
function renderizarAgendamientos() {
    const {appointments,slots}=eventosCalendario();
    const day=calendarState.day||fechaCalendario(new Date());
    document.querySelector('#appointmentsCount').textContent=appointments.length;
    const date=new Date(day+'T12:00:00');
    document.querySelector('#calendarDayTitle').textContent=new Intl.DateTimeFormat('es-CL',{day:'numeric',month:'long'}).format(date);
    const entries=appointments.filter(a=>fechaCalendario(a.fecha)===day).sort((a,b)=>new Date(a.fecha)-new Date(b.fecha));
    const times=slots.filter(s=>fechaCalendario(s.fecha)===day).sort((a,b)=>new Date(a.fecha)-new Date(b.fecha));
    const html=entries.map(a=>`<article class="calendar-event"><span class="calendar-event-time">${horaCalendario(a.fecha)}</span><div><strong>${escaparHTML(obtenerProfesional(a.profesionalId)?.nombre||'Profesional')}</strong><p>${escaparHTML(obtenerServicio(a.servicioId)?.titulo||'Servicio registrado')}</p><small>${escaparHTML(obtenerEmpresa(a.empresaId)?.nombre||'Empresa')} · ${escaparHTML(obtenerTextoEstado(a.estado))}</small><div class="calendar-event-actions">${a.estado==='propuesto'||a.estado==='confirmado'?`<button class="btn ghost" data-action="avanzar-servicio" data-id="${escaparHTML(a.id)}">${a.estado==='propuesto'?'Confirmar':'Marcar realizado'}</button>`:''}${pagos.find(p=>p.agendaId===a.id)?`<button class="btn ghost" data-action="ver-pago" data-id="${escaparHTML(pagos.find(p=>p.agendaId===a.id).id)}">Ver seguimiento</button>`:''}</div></div></article>`).join('');
    const slotsHTML=times.filter(s=>!s.ocupado).map(s=>`<button type="button" class="calendar-free-slot" ${s.habilitado?`data-action="seleccionar-horario" data-profesional="${escaparHTML(s.profesionalId)}" data-fecha="${escaparHTML(s.fecha)}"`:'disabled'}><span>${horaCalendario(s.fecha)}</span><span>${escaparHTML(s.nombre)}<small>${s.habilitado?'Disponible para una solicitud aceptada':'Pendiente de validación'}</small></span><span aria-hidden="true">↗</span></button>`).join('');
    document.querySelector('#appointmentsList').innerHTML=(html?`<h3 class="calendar-detail-label">Agendamientos</h3>${html}`:'')+(slotsHTML?`<h3 class="calendar-detail-label">Disponibilidad</h3>${slotsHTML}`:'')||'<div class="calendar-day-empty"><span aria-hidden="true">□</span><strong>Sin actividades este día</strong><p>No hay reservas ni horarios publicados para la selección actual. Puedes elegir otro día, consultar el historial o añadir disponibilidad.</p></div>';
}
function elegirDiaCalendario(day) {if(!/^\d{4}-\d{2}-\d{2}$/.test(day||''))return;calendarState.day=day;calendarState.month=day.slice(0,7);renderizarCalendario();}
function moverMesCalendario(step) {const [y,m]=calendarState.month.split('-').map(Number),next=new Date(y,m-1+step,1);elegirDiaCalendario(partesDia(next));}
function gestionarHorariosCalendario() {
    if(!profesionales.length){mostrarToast('Primero registra un profesional.');return;}
    let selected=document.querySelector('#calendarProfessional').value;
    if(!profesionales.some(p=>p.id===selected))selected=profesionales.find(p=>p.estado==='validado')?.id||profesionales[0].id;
    abrirModal(`<span class="eyebrow">DISPONIBILIDAD</span><h1 id="modalTitle">Gestionar horarios</h1><p class="muted">Publica horarios reales para los próximos 180 días. Guardarlos no crea reservas: una empresa debe tener una solicitud aceptada para agendar.</p><form id="calendarAvailabilityForm" class="form"><label>Profesional<select id="availabilityProfessional">${profesionales.map(p=>`<option value="${escaparHTML(p.id)}" ${p.id===selected?'selected':''}>${escaparHTML(p.nombre)}</option>`).join('')}</select></label><label>Fecha y hora<input id="adminAvailabilityDate" type="datetime-local"></label><button class="btn ghost" id="adminAddSlot" type="button">Añadir horario</button><ul id="adminAvailabilitySlots" class="availability-editor-list"></ul><p id="workflowError" class="workflow-error" role="alert"></p><button type="submit" class="btn primary">Guardar disponibilidad</button></form>`);
    let values=[];
    const paint=()=>{document.querySelector('#adminAvailabilitySlots').innerHTML=values.map((s,i)=>`<li><span>${escaparHTML(formatoFecha(s))}</span><button type="button" data-remove-admin-slot="${i}" aria-label="Quitar horario ${escaparHTML(formatoFecha(s))}">Quitar</button></li>`).join('')||'<li class="muted">Aún no hay horarios futuros. Añade una fecha para comenzar.</li>';};
    const load=()=>{selected=document.querySelector('#availabilityProfessional').value;values=(obtenerProfesional(selected).disponibilidad||[]).filter(s=>new Date(s)>new Date()).map(s=>new Date(s).toISOString());paint();};load();
    document.querySelector('#availabilityProfessional').onchange=load;
    document.querySelector('#adminAvailabilitySlots').onclick=e=>{const b=e.target.closest('[data-remove-admin-slot]');if(b){values.splice(Number(b.dataset.removeAdminSlot),1);paint();}};
    document.querySelector('#adminAddSlot').onclick=()=>{const date=new Date(document.querySelector('#adminAvailabilityDate').value),error=document.querySelector('#workflowError');if(!Number.isFinite(date.getTime())||date<=new Date()||date>new Date(Date.now()+180*86400000)){error.textContent='Selecciona un horario futuro dentro de los próximos 180 días.';return;}if(values.length>=100){error.textContent='Puedes publicar hasta 100 horarios.';return;}const value=date.toISOString();if(!values.includes(value))values.push(value);values.sort((a,b)=>Date.parse(a)-Date.parse(b));document.querySelector('#adminAvailabilityDate').value='';error.textContent='';paint();};
    document.querySelector('#calendarAvailabilityForm').onsubmit=async e=>{e.preventDefault();const firstFree=values.find(s=>!slotOcupado(selected,s));const day=firstFree?fechaCalendario(firstFree):values[0]?fechaCalendario(values[0]):fechaCalendario(new Date());await ejecutarWorkflow(`/api/profesionales/${encodeURIComponent(selected)}/disponibilidad/`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:versiones.profesionales[selected],horarios:values})},()=>{document.querySelector('#calendarProfessional').value=selected;elegirDiaCalendario(day);});};
}
document.addEventListener('DOMContentLoaded',()=>{
    document.querySelector('#calendarPrevMonth').onclick=()=>moverMesCalendario(-1);
    document.querySelector('#calendarNextMonth').onclick=()=>moverMesCalendario(1);
    document.querySelector('#calendarToday').onclick=()=>elegirDiaCalendario(fechaCalendario(new Date()));
    document.querySelector('#calendarMonth').onchange=e=>{if(/^\d{4}-\d{2}$/.test(e.target.value))elegirDiaCalendario(e.target.value+'-01');};
    for(const id of ['calendarHistory','calendarNextActivity'])document.querySelector('#'+id).onclick=e=>elegirDiaCalendario(e.currentTarget.dataset.day);
    document.querySelector('#calendarManageAvailability').onclick=gestionarHorariosCalendario;
    document.querySelector('#calendarGrid').addEventListener('click',e=>{const day=e.target.closest('[data-calendar-day]');if(day)elegirDiaCalendario(day.dataset.calendarDay);});
});
