/* Areej V18.15 permanent instant-update UX */
(function(){
  async function applyAreejUpdate(interactive){
    const r = await call('check_program_update');
    if(!r || !r.ok) return false;

    if(!r.configured){
      if(interactive) toast('مصدر تحديث البرنامج غير مضبوط.','warn');
      return false;
    }

    if(!r.available){
      if(interactive) toast('البرنامج على آخر إصدار V' + r.current_version);
      return false;
    }

    if(interactive){
      const note = r.notes ? '\n\n' + r.notes : '';
      if(!confirm(
        'يوجد تحديث V' + r.latest_version +
        '\nالإصدار الحالي V' + r.current_version +
        note +
        '\n\nتثبيت التحديث الآن؟'
      )) return false;
    }

    const x = await call('apply_program_update');
    if(!x || !x.ok || !x.updated) return false;

    if(x.hot_reload && !x.restarting){
      toast('✅ تم تثبيت V' + x.version + ' — جاري تحديث الواجهة فقط');
      setTimeout(function(){
        window.location.reload();
      }, 120);
      return true;
    }

    toast('تم تثبيت V' + x.version + '. هذا التحديث يتضمن ملفات تشغيل أساسية، لذلك سيتم إعادة تشغيل البرنامج مرة واحدة.');
    return true;
  }

  window.areejApplyProgramUpdate = applyAreejUpdate;

  /* Top refresh button: prefer update; otherwise refresh library data. */
  const refreshBtn = document.getElementById('refreshBtn');
  if(refreshBtn){
    refreshBtn.onclick = async function(e){
      if(e) e.preventDefault();
      const updated = await applyAreejUpdate(false);
      if(!updated) await forceProgramRefresh(true);
    };
  }

  /* The settings dialog is created dynamically by app.js and attaches its
     old click handler each time. Capture the click before that handler so all
     future checks use the permanent hot-update path. */
  document.addEventListener('click', function(e){
    const btn = e.target && e.target.closest
      ? e.target.closest('#checkProgramUpdateBtn')
      : null;
    if(!btn) return;

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    applyAreejUpdate(true);
  }, true);
})();