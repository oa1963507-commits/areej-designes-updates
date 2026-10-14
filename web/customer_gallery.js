/* Areej V18.9 - customer-facing design gallery */
(function(){
  const PAGE_SIZE=60;
  let allDesigns=[];
  let filteredDesigns=[];
  let renderedCount=0;
  let observer=null;
  let choosing=false;

  const previousRenderDesigns=window.renderDesigns;

  function norm(v){
    return String(v??'').trim().toLocaleLowerCase('ar');
  }

  function formatCustomerPrice(value){
    const n=Number(value||0);
    return Number.isFinite(n)
      ? n.toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:2})
      : '0';
  }

  function syncList(list){
    allDesigns=Array.isArray(list)?list.slice():[];
    if(document.body.classList.contains('customer-mode')){
      filterAndRender();
    }
  }

  window.renderDesigns=function(list){
    syncList(list);
    return previousRenderDesigns(list);
  };

  function filterAndRender(){
    const q=norm($('#customerSearch')?.value);
    filteredDesigns=!q?allDesigns:allDesigns.filter(d=>{
      return norm(d.serial).includes(q)||norm(d.name).includes(q);
    });
    renderedCount=0;
    const grid=$('#customerDesignGrid');
    if(grid)grid.innerHTML='';
    const count=$('#customerGalleryCount');
    if(count)count.textContent=`${filteredDesigns.length} تصميم`;
    const empty=$('#customerGalleryEmpty');
    if(empty)empty.hidden=filteredDesigns.length>0;
    appendNext();
  }

  function makeCard(d){
    const card=document.createElement('article');
    card.className='customer-design-card'+(Number(d.id)===Number(state.designId)?' current':'');
    card.tabIndex=0;
    card.dataset.designId=String(d.id);
    card.setAttribute('role','button');
    card.setAttribute('aria-label',`اختيار ${d.name||d.serial||'التصميم'} للتنفيذ`);

    const image=d.thumb
      ? `<img src="${d.thumb}" loading="lazy" decoding="async" alt="${esc(d.name||d.serial||'تصميم')}">`
      : '<div class="no-preview">NO PREVIEW</div>';

    card.innerHTML=`
      <div class="customer-design-image">
        ${image}
        <b class="customer-selected-badge">مختار للتنفيذ</b>
        <div class="customer-price-badge" title="سعر التصميم">
          <span>السعر</span>
          <strong>${formatCustomerPrice(d.price)}</strong>
          <em>ج.م</em>
        </div>
      </div>
      <div class="customer-design-meta">
        <div class="customer-design-serial"><span>السيريال</span><b>${esc(d.serial||'—')}</b></div>
        <strong class="customer-design-name" title="${esc(d.name||'بدون اسم')}">${esc(d.name||'بدون اسم')}</strong>
        <span>اضغط لاختيار التصميم للتنفيذ</span>
      </div>
    `;

    const choose=()=>chooseDesign(d,card);
    card.onclick=choose;
    card.onkeydown=e=>{
      if(e.key==='Enter'||e.key===' '){
        e.preventDefault();
        choose();
      }
    };
    return card;
  }

  function appendNext(){
    const grid=$('#customerDesignGrid');
    if(!grid||renderedCount>=filteredDesigns.length)return;
    const end=Math.min(renderedCount+PAGE_SIZE,filteredDesigns.length);
    const frag=document.createDocumentFragment();
    for(let i=renderedCount;i<end;i++)frag.appendChild(makeCard(filteredDesigns[i]));
    grid.appendChild(frag);
    renderedCount=end;
  }

  async function fetchAllDesigns(){
    const qty=parseInt($('#quantityInput')?.value||'0')||0;
    const r=await call('get_state','',state.designId,qty,false);
    if(!r?.ok)return false;

    setNetwork(true);
    state.revision=r.revision;
    state.latest=r.latest_activity;
    state.libraryRoot=r.library_root||state.libraryRoot;
    state.designId=r.selected?.id||state.designId||null;
    state.fileSignature=r.file_signature||'';
    if(r.security)applySecurity(r.security);
    updateHistoryUI(r.history);

    window.renderDesigns(r.designs||[]);
    renderSelected(r.selected,r.files||[],r.materials||[]);
    setUnread(r.unread||0);
    return true;
  }

  async function openGallery(){
    closeDrawer();
    state.favorites=false;
    state.query='';
    if($('#sidebarSearch'))$('#sidebarSearch').value='';

    const page=$('#customerGalleryPage');
    if(!page)return;
    page.hidden=false;
    document.body.classList.add('customer-mode');

    const input=$('#customerSearch');
    if(input)input.value='';
    const empty=$('#customerGalleryEmpty');
    if(empty){empty.hidden=true;empty.textContent='جاري تحميل التصميمات...'}
    const grid=$('#customerDesignGrid');
    if(grid)grid.innerHTML='';

    const ok=await fetchAllDesigns();
    if(empty)empty.textContent='لا توجد تصميمات مطابقة';
    if(!ok){
      document.body.classList.remove('customer-mode');
      page.hidden=true;
      return;
    }
    filterAndRender();
    if(input)setTimeout(()=>input.focus(),0);
  }

  function closeGallery(){
    document.body.classList.remove('customer-mode');
    const page=$('#customerGalleryPage');
    if(page)page.hidden=true;
    window.scrollTo({top:0,behavior:'auto'});
  }

  async function chooseDesign(d,card){
    if(choosing)return;
    choosing=true;
    card?.classList.add('current');
    const qty=parseInt($('#quantityInput')?.value||'0')||0;

    try{
      const r=await call('get_state',String(d.serial||''),d.id,qty,false);
      if(!r?.ok)return;

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

      /* Repaint the hidden sidebar once with the already cached full list,
         so returning to production is instant and the chosen design is active. */
      window.renderDesigns(allDesigns);
      closeGallery();

      const chosenName=d.name||d.serial||'التصميم';
      toast(`تم اختيار ${chosenName} للتنفيذ`);
    }finally{
      choosing=false;
    }
  }

  function setup(){
    const nav=$('#customerGalleryNav');
    const back=$('#customerBackBtn');
    const search=$('#customerSearch');
    const sentinel=$('#customerGallerySentinel');

    if(nav)nav.onclick=openGallery;
    if(back)back.onclick=closeGallery;
    if(search){
      let timer=null;
      search.oninput=()=>{
        clearTimeout(timer);
        timer=setTimeout(filterAndRender,60);
      };
    }

    if('IntersectionObserver' in window&&sentinel){
      observer=new IntersectionObserver(entries=>{
        if(entries.some(x=>x.isIntersecting)&&document.body.classList.contains('customer-mode')){
          appendNext();
        }
      },{rootMargin:'700px 0px'});
      observer.observe(sentinel);
    }else{
      window.addEventListener('scroll',()=>{
        if(!document.body.classList.contains('customer-mode'))return;
        if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-800)appendNext();
      },{passive:true});
    }

    document.addEventListener('keydown',e=>{
      if(e.key==='Escape'&&document.body.classList.contains('customer-mode')){
        closeGallery();
      }
    });
  }

  setup();
})();
