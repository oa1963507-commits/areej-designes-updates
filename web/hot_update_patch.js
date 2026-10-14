/* Areej V18.13 instant UI update helper */
(function(){
  const applyUpdate = async function(interactive){
    const r = await call('check_program_update');
    if(!r || !r.ok) return false;

    if(!r.configured){
      if(interactive) toast('مصدر تحديث البرنامج غير مضبوط. اضبطه من إعدادات الـOwner.','warn');
      return false;
    }

    if(!r.available){
      if(interactive) toast('البرنامج على آخر إصدار V' + r.current_version);
      return false;
    }

    if(interactive){
      const note = r.notes ? '\n\n' + r.notes : '';
      const ok = confirm(
        'يوجد تحديث V' + r.latest_version +
        '\nالإصدار الحالي V' + r.current_version +
        note +
        '\n\nتثبيت التحديث الآن؟'
      );
      if(!ok) return false;
    }

    const x = await call('apply_program_update');
    if(!x || !x.ok || !x.updated) return false;

    if(x.hot_reload && !x.restarting){
      toast('تم تثبيت V' + x.version + ' — جاري إظهار التعديل الآن');
      setTimeout(function(){
        window.location.reload();
      }, 180);
      return true;
    }

    toast('تم تحميل V' + x.version + '. سيتم إعادة تشغيل البرنامج لأن التحديث يتضمن ملفات تشغيل أساسية.');
    return true;
  };

  window.checkAndApplyProgramUpdate = applyUpdate;
  window.topRefreshAction = async function(){
    const updated = await applyUpdate(false);
    if(updated) return;
    await forceProgramRefresh(true);
  };

  const btn = document.getElementById('refreshBtn');
  if(btn) btn.onclick = window.topRefreshAction;
})();