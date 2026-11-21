(() => {
  'use strict';
  document.querySelectorAll('[data-signature-preview]').forEach(card => {
    const field = document.getElementById(card.dataset.signaturePreview);
    if (!field) return;
    const update = () => {
      const name = field.value.trim();
      card.querySelectorAll('[data-signature-name]').forEach(label => {
        label.textContent = name || 'Your full name';
      });
    };
    field.addEventListener('input', update);
    field.addEventListener('change', update);
    window.addEventListener('pageshow', update);
    update();
  });
})();
