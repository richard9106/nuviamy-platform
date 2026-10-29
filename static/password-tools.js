(() => {
  'use strict';
  // The server enforces these rules. No password is stored, logged or sent here.
  const formatChecks = (value, minimum) => ({
    length: Array.from(value).length >= minimum,
    lowercase: /\p{Ll}/u.test(value),
    uppercase: /\p{Lu}/u.test(value),
    number: /\p{Nd}/u.test(value),
    special: /[\p{P}\p{S}]/u.test(value),
  });
  document.querySelectorAll('[data-password-control]').forEach(control => {
    const input = control.querySelector('input');
    const toggle = control.querySelector('[data-password-toggle]');
    if (!input || !toggle) return;
    toggle.hidden = false;
    toggle.addEventListener('click', () => {
      const revealed = input.type === 'password';
      input.type = revealed ? 'text' : 'password';
      toggle.setAttribute('aria-pressed', String(revealed));
      toggle.setAttribute('aria-label', revealed ? toggle.dataset.hideLabel : toggle.dataset.showLabel);
      toggle.querySelector('[data-password-eye]').hidden = revealed;
      toggle.querySelector('[data-password-eye-off]').hidden = !revealed;
    });
    // Returning through browser history must not leave a revealed password.
    window.addEventListener('pageshow', () => {
      input.type = 'password';
      toggle.setAttribute('aria-pressed', 'false');
      toggle.setAttribute('aria-label', toggle.dataset.showLabel);
      toggle.querySelector('[data-password-eye]').hidden = false;
      toggle.querySelector('[data-password-eye-off]').hidden = true;
    });
  });
  document.querySelectorAll('[data-password-requirements]').forEach(panel => {
    const input = document.getElementById(panel.dataset.passwordInput);
    if (!input) return;
    const update = () => {
      const checks = formatChecks(input.value, Number(input.dataset.passwordMinimum || 8));
      panel.querySelectorAll('[data-password-rule]').forEach(item => {
        const met = checks[item.dataset.passwordRule];
        item.classList.toggle('is-met', met);
        item.querySelector('[data-password-rule-icon]').textContent = met ? '✓' : '○';
        item.querySelector('[data-password-rule-status]').textContent = met ? 'Met: ' : 'Needed: ';
      });
      const count = Object.values(checks).filter(Boolean).length;
      const text = !input.value ? 'Use a unique password without personal information.' :
        count === 5 ? 'All format requirements met. Avoid common or reused passwords.' :
          `${count} of 5 format requirements met.`;
      const summary = panel.querySelector('[data-password-summary]');
      if (summary.textContent !== text) summary.textContent = text;
    };
    input.addEventListener('input', update);
    input.addEventListener('change', update);
    window.addEventListener('pageshow', update);
    update();
  });
})();
