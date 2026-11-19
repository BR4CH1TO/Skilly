/* Búsqueda global de administración: resultados visibles mientras se escribe. */
let globalSearchActive = -1;
function buscarRegistrosGlobales(value) {
    const query=normalizar(value);
    if(!query)return [];
    const match=parts=>normalizar(parts.filter(Boolean).join(' ')).includes(query);
    return [
        ...profesionales.filter(p=>match([p.nombre,p.profesion,p.especialidad,p.ubicacion])).map(p=>({id:p.id,title:p.nombre,subtitle:p.profesion,kind:'Profesional',action:'ver-perfil'})),
        ...empresas.filter(e=>match([e.nombre,e.rubro,e.contacto,e.correo])).map(e=>({id:e.id,title:e.nombre,subtitle:e.rubro||e.contacto||'Empresa registrada',kind:'Empresa',action:'ver-empresa'})),
        ...servicios.filter(s=>match([s.titulo,s.categoria,obtenerProfesional(s.profesionalId)?.nombre])).map(s=>({id:s.id,title:s.titulo,subtitle:obtenerProfesional(s.profesionalId)?.nombre||s.categoria,kind:'Servicio',action:'ver-servicio'}))
    ];
}
function cerrarBusquedaGlobal() {
    const list=document.querySelector('#globalSearchResults');if(list)list.hidden=true;
    const input=document.querySelector('#globalSearch');if(input){input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
    globalSearchActive=-1;
}
function opcionBusquedaHTML(result,index) {
    return `<button type="button" role="option" aria-selected="false" id="globalResult-${index}" class="global-search-option" data-action="${result.action}" data-id="${escaparHTML(result.id)}"><span class="global-search-symbol" aria-hidden="true">${result.kind==='Empresa'?'▦':result.kind==='Servicio'?'◇':'◎'}</span><span class="global-search-copy"><strong>${escaparHTML(result.title)}</strong><small>${escaparHTML(result.subtitle)}</small></span><span class="global-search-kind">${result.kind}</span></button>`;
}
function mostrarSugerenciasGlobales() {
    const input=document.querySelector('#globalSearch'),list=document.querySelector('#globalSearchResults');
    if(!list||!input)return;
    if(document.querySelector("#modal")?.open){cerrarBusquedaGlobal();return;}
    if(!input.value.trim()){cerrarBusquedaGlobal();return;}
    const results=buscarRegistrosGlobales(input.value);
    globalSearchActive=-1;
    list.innerHTML=`<div class="global-search-caption">${results.length} resultado${results.length===1?'':'s'} en todo Skilly</div>${results.slice(0,8).map((result,index)=>opcionBusquedaHTML(result,index)).join('')||'<div class="global-search-empty">No encontramos coincidencias. Prueba con el nombre, profesión o empresa.</div>'}${results.length>8?'<button type="button" class="global-search-all">Ver todos los resultados →</button>':''}`;
    list.hidden=false;input.setAttribute('aria-expanded','true');input.removeAttribute('aria-activedescendant');
    const all=list.querySelector('.global-search-all');if(all)all.onclick=abrirBusquedaGlobal;
}
function abrirBusquedaGlobal() {
    const query=document.querySelector('#globalSearch').value.trim();if(!query){document.querySelector('#globalSearch').focus();return;}
    const results=buscarRegistrosGlobales(query);cerrarBusquedaGlobal();
    abrirModal(`<span class="eyebrow">BÚSQUEDA GLOBAL</span><h1 id="modalTitle">Resultados para “${escaparHTML(query)}”</h1><p class="muted">${results.length} coincidencias entre profesionales, empresas y servicios.</p><div class="search-results">${results.map(r=>`<button class="search-result" data-action="${r.action}" data-id="${escaparHTML(r.id)}"><strong>${escaparHTML(r.title)}</strong><span>${r.kind} · ${escaparHTML(r.subtitle)}</span></button>`).join('')||'<p class="global-search-empty">No hay coincidencias con esa búsqueda. Puedes buscar por nombre, rubro, profesión o contacto.</p>'}</div>`);
}
document.addEventListener('DOMContentLoaded',()=>{
    const input=document.querySelector('#globalSearch');if(!input)return;
    input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls','globalSearchResults');input.setAttribute('aria-expanded','false');
    input.addEventListener('input',debounce(mostrarSugerenciasGlobales,120));input.addEventListener('focus',mostrarSugerenciasGlobales);
    document.querySelector('#globalSearchSubmit').onclick=abrirBusquedaGlobal;
    input.addEventListener('keydown',event=>{
        const list=document.querySelector('#globalSearchResults');let options=[...list.querySelectorAll('[role=option]')];
        if(event.key==='Escape'){cerrarBusquedaGlobal();event.preventDefault();return;}
        if(event.key==='Enter'){event.preventDefault();if(!list.hidden&&globalSearchActive>=0){options[globalSearchActive]?.click();cerrarBusquedaGlobal();}else abrirBusquedaGlobal();return;}
        if(!['ArrowDown','ArrowUp'].includes(event.key))return;
        event.preventDefault();if(list.hidden){mostrarSugerenciasGlobales();options=[...list.querySelectorAll('[role=option]')];}if(!options.length)return;
        globalSearchActive=(globalSearchActive+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;
        options.forEach((o,i)=>o.setAttribute('aria-selected',String(i===globalSearchActive)));
        input.setAttribute('aria-activedescendant',options[globalSearchActive].id);options[globalSearchActive].scrollIntoView({block:'nearest'});
    });
});
document.addEventListener('click',event=>{
    if(event.target.closest('#globalSearchResults [data-action]'))cerrarBusquedaGlobal();
    else if(!event.target.closest('.admin-global-search'))cerrarBusquedaGlobal();
});
