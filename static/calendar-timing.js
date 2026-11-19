(() => {
  const items = [...document.querySelectorAll('[data-calendar-timing]')];
  const labels = { past: 'Past session', soon: 'In progress or starts within 24 hours', future: 'More than 24 hours away', cancelled: 'Cancelled', no_show: 'No show' };
  const originals = new WeakMap(items.map(item => [item, { title: item.getAttribute('title') || '', aria: item.getAttribute('aria-label') || '' }]));
  const refresh = () => {
    const now = Date.now();
    items.forEach(item => {
      const start = Date.parse(item.dataset.startsAt);
      const end = Date.parse(item.dataset.endsAt);
      if (!Number.isFinite(start) || !Number.isFinite(end)) return;
      const status = item.dataset.sessionStatus;
      const phase = ['cancelled', 'no_show'].includes(status) ? status : end <= now ? 'past' : start <= now + 86400000 ? 'soon' : 'future';
      Object.keys(labels).forEach(value => item.classList.toggle(`calendar-timing-${value}`, value === phase));
      const original = originals.get(item);
      item.title = [original.title, labels[phase]].filter(Boolean).join(' · ');
      if (original.aria) item.setAttribute('aria-label', `${original.aria} · ${labels[phase]}`);
    });
  };
  refresh();
  if (items.length) {
    window.setInterval(refresh, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  }
})();
