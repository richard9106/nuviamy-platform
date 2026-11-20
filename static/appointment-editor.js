(() => {
  const drawers = [...document.querySelectorAll('[data-appointment-drawer]')];
  const snapshots = new WeakMap();
  let trigger = null;
  const fingerprint = dialog => JSON.stringify([...dialog.querySelectorAll('form')].map(form => [...new FormData(form)].filter(([name]) => !['csrfmiddlewaretoken', 'next'].includes(name))));
  const changed = dialog => dialog.open && snapshots.has(dialog) && fingerprint(dialog) !== snapshots.get(dialog).fingerprint;
  const mayDiscard = dialog => !changed(dialog) || window.confirm('Discard your unsaved calendar changes?');
  const restore = dialog => {
    const saved = snapshots.get(dialog);
    if (!saved) return;
    saved.client.replaceChildren(...saved.options);
    saved.values.forEach(([el, value, checked]) => { el.value = value; if (typeof checked === 'boolean') el.checked = checked; });
    dialog.dispatchEvent(new Event('appointment:restored'));
  };
  drawers.forEach(dialog => {
    const form = dialog.querySelector('form');
    const start = form.elements.starts_at;
    const end = form.elements.ends_at;
    const tabs = [...dialog.querySelectorAll('[data-editor-tab]')];
    const panels = [...dialog.querySelectorAll('[data-editor-panel]')];
    const selectTab = name => {
      if (dialog.id === 'appointment-create-modal') dialog.querySelector('.modal-head h2').textContent = { appointment: 'Schedule a session', event: 'Calendar event', 'out-of-office': 'Out of office', availability: 'Practice availability' }[name];
      tabs.forEach(tab => { const selected = tab.dataset.editorTab === name; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; });
      panels.forEach(panel => { panel.hidden = panel.dataset.editorPanel !== name; });
    };
    tabs.forEach((tab, index) => {
      const name = tab.dataset.editorTab;
      const panel = panels.find(panel => panel.dataset.editorPanel === name);
      tab.id = `${dialog.id}-tab-${name}`;
      if (panel) { panel.id = `${dialog.id}-panel-${name}`; panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', tab.id); tab.setAttribute('aria-controls', panel.id); }
      tab.addEventListener('click', () => selectTab(name));
      tab.addEventListener('keydown', event => {
        let next = index;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        else return;
        event.preventDefault(); selectTab(tabs[next].dataset.editorTab); tabs[next].focus();
      });
    });
    const updateDuration = () => {
      const minutes = (new Date(end.value) - new Date(start.value)) / 60000;
      form.querySelector('[data-duration-label]').textContent = minutes > 0 ? `${minutes} min` : '';
      form.querySelectorAll('[data-duration-minutes]').forEach(button => button.setAttribute('aria-pressed', String(minutes === Number(button.dataset.durationMinutes))));
    };
    form.querySelectorAll('[data-duration-minutes]').forEach(button => button.addEventListener('click', () => {
      if (!start.value) { start.focus(); return; }
      const value = new Date(start.value);
      if (Number.isNaN(value.getTime())) return;
      value.setMinutes(value.getMinutes() + Number(button.dataset.durationMinutes));
      end.value = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}T${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`;
      end.dispatchEvent(new Event('change', { bubbles: true }));
    }));
    form.addEventListener('change', updateDuration);
    form.addEventListener('input', updateDuration);
    dialog.addEventListener('invalid', event => {
      const panel = event.target.closest('[data-editor-panel]');
      if (panel) selectTab(panel.dataset.editorPanel);
      const progressive = event.target.closest('[data-appointment-details]');
      if (progressive) progressive.hidden = false;
      const details = event.target.closest('details');
      if (details) details.open = true;
    }, true);
    const search = form.querySelector('[data-client-search]');
    const client = form.elements.client;
    const choices = [...client.options];
    const revealDetails = () => form.querySelectorAll('[data-appointment-details]').forEach(el => { el.hidden = !client.value; });
    client.addEventListener('change', revealDetails);
    const filterClients = () => {
      const query = search.value.trim().toLocaleLowerCase();
      const selected = client.value;
      const matches = choices.filter(option => !option.value || option.textContent.toLocaleLowerCase().includes(query));
      client.replaceChildren(...choices.filter(option => matches.includes(option) || option.value === selected));
      client.value = selected;
      const status = form.querySelector('[data-client-search-status]');
      status.hidden = !query;
      const count = matches.filter(option => option.value).length;
      status.textContent = count ? `${count} matching client${count === 1 ? '' : 's'}.` : 'No matching clients. Your current selection is unchanged.';
    };
    search.addEventListener('input', filterClients);
    new MutationObserver(() => {
      if (!dialog.open) return;
      requestAnimationFrame(() => {
        if (!dialog.open) return;
        if (trigger?.dataset.availabilityDate) {
          start.value = `${trigger.dataset.availabilityDate}T09:00`;
          end.value = `${trigger.dataset.availabilityDate}T09:50`;
        }
        dialog.querySelectorAll('[data-calendar-operation]').forEach(operation => {
          if (operation.dataset.calendarOperation === 'event') {
            operation.elements.starts_at.value = start.value;
            operation.elements.ends_at.value = end.value;
          } else {
            operation.elements.date.value = trigger?.dataset.availabilityDate || start.value.slice(0, 10);
            operation.elements.starts_at.value = operation.dataset.calendarOperation === 'availability' ? '09:00' : '';
            operation.elements.ends_at.value = operation.dataset.calendarOperation === 'availability' ? '17:00' : '';
          }
        });
        selectTab(trigger?.dataset.editorOpen || 'appointment');
        revealDetails(); updateDuration();
        snapshots.set(dialog, { fingerprint: fingerprint(dialog), client, options: [...client.options], values: [...dialog.querySelectorAll('input, select, textarea')].filter(el => el.name).map(el => [el, el.value, el.checked]) });
        if (window.innerWidth > 720) {
          const left = Math.max(16, Math.min((trigger?.getBoundingClientRect().left || window.innerWidth / 2) + 12, window.innerWidth - 496));
          dialog.style.setProperty('--editor-left', `${left}px`);
        }
      });
    }).observe(dialog, { attributes: true, attributeFilter: ['open'] });
    dialog.addEventListener('cancel', event => { if (!mayDiscard(dialog)) event.preventDefault(); });
    dialog.addEventListener('close', () => {
      client.replaceChildren(...choices); restore(dialog); snapshots.delete(dialog);
      search.value = ''; filterClients(); revealDetails(); selectTab('appointment');
      dialog.querySelectorAll('details').forEach(details => { details.open = false; });
      updateDuration();
    });
    dialog.querySelectorAll('form').forEach(operation => operation.addEventListener('submit', event => {
      if (event.defaultPrevented) return;
      try { sessionStorage.setItem('nuviamy.calendar.scroll', JSON.stringify({ x: window.scrollX, y: window.scrollY, at: Date.now() })); } catch (_) { /* Optional viewport storage. */ }
      snapshots.delete(dialog);
    }));
    updateDuration();
  });
  // Legacy availability launch for workspaces without appointment creation permission.
  document.querySelectorAll('[data-availability-mode]').forEach(button => button.addEventListener('click', () => {
    const dialog = button.closest('dialog');
    dialog.querySelector('[name="is_available"]').checked = button.dataset.availabilityMode === 'available';
    dialog.querySelectorAll('[data-availability-mode]').forEach(tab => tab.setAttribute('aria-selected', String(tab === button)));
  }));
  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-modal-target]');
    if (opener) trigger = opener;
    else if (event.target.closest('.gcal-day-column') && !event.target.closest('a, button, input, select, textarea')) trigger = null;
    const dialog = event.target.closest('[data-appointment-drawer]');
    if (!dialog) return;
    if (event.target === dialog || event.target.closest('[data-modal-close], [data-reschedule-url], [data-note-popup], a[href]')) {
      if (!mayDiscard(dialog)) { event.preventDefault(); event.stopImmediatePropagation(); }
      else if (changed(dialog)) restore(dialog);
    }
  }, true);
  window.addEventListener('beforeunload', event => { if (drawers.some(changed)) { event.preventDefault(); event.returnValue = ''; } });
  try {
    const saved = JSON.parse(sessionStorage.getItem('nuviamy.calendar.scroll') || 'null');
    sessionStorage.removeItem('nuviamy.calendar.scroll');
    if (saved && Date.now() - saved.at < 60000) requestAnimationFrame(() => window.scrollTo(saved.x, saved.y));
  } catch (_) { /* Optional viewport storage. */ }
})();
