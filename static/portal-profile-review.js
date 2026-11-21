(() => {
  'use strict';
  const form = document.querySelector('[data-profile-review]');
  if (!form) return;
  const fields = form.querySelector('[data-profile-fields]');
  const summary = form.querySelector('[data-profile-summary]');
  const list = form.querySelector('[data-profile-summary-list]');
  const confirm = form.querySelector('[data-profile-confirm]');
  const confirmInput = confirm.querySelector('input');
  const next = form.querySelector('[data-profile-next]');
  const back = form.querySelector('[data-profile-back]');
  const submit = form.querySelector('[data-profile-submit]');
  let reviewing = false;
  const show = value => {
    reviewing = value;
    fields.hidden = value;
    summary.hidden = !value;
    confirm.hidden = !value;
    confirmInput.disabled = !value;
    next.hidden = value;
    back.hidden = !value;
    submit.hidden = !value;
  };
  next.addEventListener('click', () => {
    const controls = [...fields.querySelectorAll('input,select,textarea')];
    for (const field of controls) if (!field.reportValidity()) return;
    list.replaceChildren();
    controls.forEach(field => {
      if (['hidden','button'].includes(field.type)) return;
      if (field.type === 'file' && !field.files.length) return;
      if (!field.value && !field.defaultValue && field.type !== 'checkbox') return;
      if (field.type === 'checkbox' && !field.checked && !field.defaultChecked) return;
      const row = document.createElement('div');
      const title = document.createElement('dt');
      const value = document.createElement('dd');
      title.textContent = field.labels?.[0]?.textContent || field.name;
      value.textContent = field.type === 'file' ? [...field.files].map(file => file.name).join(', ') || 'Not uploaded' :
        field.type === 'checkbox' ? (field.checked ? 'Yes' : 'No') :
        field.tagName === 'SELECT' ? field.selectedOptions[0]?.textContent || 'Not provided' : field.value || 'Not provided';
      row.append(title,value);
      list.append(row);
    });
    show(true);
    summary.querySelector('h2').focus();
  });
  back.addEventListener('click', () => { confirmInput.checked = false; show(false); next.focus(); });
  form.addEventListener('submit', event => { if (!reviewing) { event.preventDefault(); next.click(); } });
  show(false);
})();
