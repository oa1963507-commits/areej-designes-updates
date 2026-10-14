/* Areej V18.16 - show intro once per desktop app session */
(function(){
  const KEY='areej_startup_intro_seen_v1';

  function hideIntro(el){
    if(!el) return;
    el.classList.add('leave');
    setTimeout(function(){
      el.classList.remove('show','leave');
      el.setAttribute('aria-hidden','true');
    },380);
  }

  function showIntro(){
    const el=document.getElementById('startupIntro');
    if(!el) return;

    try{
      if(sessionStorage.getItem(KEY)==='1') return;
      sessionStorage.setItem(KEY,'1');
    }catch(_){}

    el.classList.add('show');
    el.setAttribute('aria-hidden','false');

    setTimeout(function(){
      hideIntro(el);
    },5000);
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',showIntro,{once:true});
  }else{
    showIntro();
  }
})();