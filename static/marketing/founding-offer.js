(() => {
  const banner = document.querySelector('[data-founding-offer]');
  if (!banner) return;
  const dismiss = banner.querySelector('[data-founding-dismiss]');
  dismiss.hidden = false;
  dismiss.addEventListener('click', () => {
    banner.hidden = true;
  });
})();
