function appointmentRecurrenceDates(startText, interval, days, mode, count, untilText) {
  const format = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const start = new Date(`${startText.slice(0,10)}T12:00:00`);
  if (Number.isNaN(start.getTime())) throw new Error('Choose a start date to preview your sessions.');
  if (!Number.isInteger(interval) || interval < 1 || interval > 12) throw new Error('Choose an interval from 1 to 12 weeks.');
  const weekdays = [...new Set(days)].sort((a,b)=>a-b);
  if (!weekdays.length || weekdays.some(day=>!Number.isInteger(day) || day < 0 || day > 6)) throw new Error('Choose at least one weekday.');
  if (!weekdays.includes((start.getDay()+6)%7)) throw new Error('Include the first appointment’s weekday, or change its start date.');
  if (mode === 'count' && (!Number.isInteger(count) || count < 1 || count > 52)) throw new Error('Choose between 1 and 52 sessions.');
  const until = new Date(`${untilText}T12:00:00`);
  if (mode === 'date' && (Number.isNaN(until.getTime()) || until < start)) throw new Error('Choose an end date on or after the first appointment.');
  const week = new Date(start); week.setDate(week.getDate()-(start.getDay()+6)%7);
  const dates = [];
  // A finite plan has at most 52 sessions, even when ending by date.
  for (let index=0; index<=52; index++) {
    for (const day of weekdays) {
      const candidate = new Date(week); candidate.setDate(candidate.getDate()+day);
      if (candidate < start) continue;
      if (mode === 'date' && candidate > until) return dates;
      dates.push(format(candidate));
      if (dates.length > 52) throw new Error('This rule creates more than 52 sessions. Choose an earlier end date or fewer weekdays.');
      if (mode === 'count' && dates.length === count) return dates;
    }
    week.setDate(week.getDate()+7*interval);
  }
  throw new Error('Choose a shorter recurrence.');
}
(() => {
  document.querySelectorAll('[data-recurrence-editor]').forEach(editor => {
    const form = editor.closest('form');
    const rule = form.elements.recurrence_rule;
    const start = form.elements.starts_at;
    const settings = editor.querySelector('[data-recurrence-settings]');
    const submit = form.querySelector('button[type="submit"]') || (form.id ? document.querySelector(`button.btn-primary[form="${form.id}"]`) : null);
    const submitLabel = submit?.textContent;
    const weekdays = [...editor.querySelectorAll('[name="recurrence_weekdays"]')];
    let customDays = weekdays.some(input=>input.checked);
    weekdays.forEach(input=>{
      input.addEventListener('input',()=>{customDays=true;});
      input.addEventListener('change',()=>{customDays=true;});
    });
    const update = () => {
      const repeating = rule.value === 'weekly';
      const mode = form.elements.recurrence_ends.value || 'count';
      settings.hidden = !repeating;
      settings.querySelectorAll('input, select').forEach(input=>{input.disabled = !repeating;});
      const byCount = mode === 'count';
      editor.querySelector('[data-recurrence-count]').hidden = !byCount;
      editor.querySelector('[data-recurrence-date]').hidden = byCount;
      form.elements.repeat_weekly_count.disabled = !repeating || !byCount;
      form.elements.repeat_weekly_count.required = repeating && byCount;
      form.elements.recurrence_interval.required = repeating;
      form.elements.recurrence_until.required = repeating && !byCount;
      form.elements.recurrence_until.disabled = !repeating || byCount;
      const date = new Date(`${start.value.slice(0,10)}T12:00:00`);
      if (!customDays && !Number.isNaN(date.getTime())) weekdays.forEach(input=>{input.checked=Number(input.value)===(date.getDay()+6)%7;});
      const title = editor.querySelector('[data-recurrence-preview-title]');
      const preview = editor.querySelector('[data-recurrence-preview-dates]');
      preview.replaceChildren();
      if (!repeating) {title.textContent='One appointment.';if(submit)submit.textContent=submitLabel;return;}
      try {
        const dates = appointmentRecurrenceDates(start.value, Number(form.elements.recurrence_interval.value), weekdays.filter(input=>input.checked).map(input=>Number(input.value)), mode, Number(form.elements.repeat_weekly_count.value), form.elements.recurrence_until.value);
        const display = value => new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'}).format(new Date(`${value}T12:00:00`));
        if(submit)submit.textContent=`Create ${dates.length} appointment${dates.length===1?'':'s'}`;
        title.textContent=`${dates.length} session${dates.length===1?'':'s'} · Last: ${display(dates.at(-1))}`;
        dates.slice(0,4).forEach(date=>{const item=document.createElement('li');item.textContent=display(date);preview.append(item);});
        if(dates.length>4){const more=document.createElement('li');more.textContent=`… and ${dates.length-4} more`;preview.append(more);}
      } catch(error) {title.textContent=error.message;if(submit)submit.textContent='Create appointments';}
    };
    form.addEventListener('input',update);
    form.addEventListener('change',update);
    const dialog = form.closest('dialog');
    if(dialog){
      new MutationObserver(()=>{if(dialog.open)update();}).observe(dialog,{attributes:true,attributeFilter:['open']});
      dialog.addEventListener('appointment:restored',()=>{customDays=false;update();});
    }
    update();
  });
})();
