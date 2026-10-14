/* Areej V18.6 navigation performance patch.
   Keep the design library DOM cached while switching between designs. */
(function(){
  async function selectDesignFast(d,el){
    if(!d||!d.id||state.designId===d.id)return;

    state.designId=d.id;
    $$('.design-item.active').forEach(x=>x.classList.remove('active'));
    if(el)el.classList.add('active');

    const qty=parseInt($('#quantityInput').value||'0')||0;

    /* get_state normally rebuilds all sidebar thumbnails. Using the clicked
       serial narrows that backend work to this design, while we keep the
       already-rendered sidebar untouched. */
    const r=await call('get_state',d.serial||'',d.id,qty,state.favorites);
    if(!r?.ok){
      setNetwork(false);
      return;
    }

    setNetwork(true);
    state.revision=r.revision;
    state.latest=r.latest_activity;
    state.libraryRoot=r.library_root||state.libraryRoot;
    state.designId=r.selected?.id||d.id;
    state.fileSignature=r.file_signature||'';
    if(r.security)applySecurity(r.security);
    updateHistoryUI(r.history);
    renderSelected(r.selected,r.files||[],r.materials||[]);
    setUnread(r.unread||0);
  }

  window.renderDesigns=function(list){
    $('#designCount').textContent=list.length;
    const box=$('#designList');
    box.innerHTML='';

    if(!list.length){
      box.innerHTML='<div class="empty-state">لا توجد تصميمات</div>';
      return;
    }

    const frag=document.createDocumentFragment();
    for(const d of list){
      const el=document.createElement('div');
      el.className='design-item'+(d.id===state.designId?' active':'');
      el.innerHTML=`${d.thumb?`<img class="design-thumb" src="${d.thumb}" loading="lazy" decoding="async">`:'<div class="design-thumb"></div>'}<div class="design-meta"><small>${esc(d.serial)}</small><strong>${esc(d.name||'بدون اسم')}</strong></div><button class="fav-star ${d.favorite?'on':''}" title="${d.favorite?'إزالة من المفضلة':'إضافة للمفضلة'}">${d.favorite?'★':'☆'}</button><span class="dots">⋮</span>`;

      el.querySelector('.fav-star').onclick=async e=>{
        e.stopPropagation();
        const r=await call('toggle_favorite',d.id);
        if(r?.ok){
          toast(r.favorite?'تمت الإضافة للمفضلة':'تمت الإزالة من المفضلة');
          refresh(true);
        }
      };

      el.onclick=e=>{
        if(e.target.classList.contains('dots')){
          designMenu(d);
          return;
        }
        selectDesignFast(d,el);
      };

      frag.appendChild(el);
    }
    box.appendChild(frag);
  };
})();
