(() => {
  'use strict';
  const form = document.querySelector('[data-form-share-wizard]');
  if (!form || form.querySelector('.form-error')) return;
  const selection = form.querySelector('[data-share-selection]');
  const email = form.querySelector('[data-share-email]');
  const next = form.querySelector('[data-share-next]');
  const back = form.querySelector('[data-share-back]');
  const review = form.querySelector('[data-share-review]');
  const steps = document.querySelectorAll('[data-share-indicator]');
  const show = second => {
    selection.hidden = second;
    email.hidden = !second;
    next.hidden = second;
    back.hidden = !second;
    review.hidden = !second;
    steps.forEach(step => Number(step.dataset.shareIndicator) === (second ? 2 : 1) ? step.setAttribute('aria-current', 'step') : step.removeAttribute('aria-current'));
  };
  next.addEventListener('click', () => {
    const selected = form.querySelector('input[name="templates"]:checked');
    const message = form.querySelector('[data-share-selection-error]');
    message.hidden = Boolean(selected);
    if (!selected) { message.focus(); return; }
    show(true);
    email.querySelector('h2').focus();
  });
  back.addEventListener('click', () => { show(false); next.focus(); });
  show(false);
})();
