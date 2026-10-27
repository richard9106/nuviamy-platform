(() => {
  document.querySelectorAll('[data-google-connection]').forEach((form) => {
    const details = form.querySelector('[data-google-privacy-details]');
    const selection = form.querySelector('[data-google-calendar-selection]');
    const calendar = selection?.querySelector('input[type="checkbox"]');
    const connect = form.querySelector('[data-google-connect]');
    const hint = form.querySelector('#google-privacy-hint');
    if (!details || !selection || !calendar || !connect || !hint) return;
    let opened = false;
    const update = () => {
      selection.disabled = !opened;
      connect.disabled = !opened || !calendar.checked || form.dataset.oauthConfigured !== 'true';
    };
    details.addEventListener('toggle', () => {
      if (details.open && !opened) {
        opened = true;
        hint.textContent = 'You can now select Google Calendar sync to continue.';
        update();
      }
    });
    calendar.addEventListener('change', update);
    // Keyboard or implicit submission must follow the same review step.
    form.addEventListener('submit', (event) => {
      if (!opened || !calendar.checked || form.dataset.oauthConfigured !== 'true') {
        event.preventDefault();
        if (!opened) details.querySelector('summary')?.focus();
      }
    });
    update();
  });
})();
