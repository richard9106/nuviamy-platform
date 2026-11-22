(() => {
  'use strict';
  const config = document.currentScript;
  const wrapForm = form => {
    if (form.classList.contains('workspace-panel-form') || form.querySelector(':scope > .client-drawer-fields')) return;
    if (!form.querySelector('input:not([type="hidden"]):not([type="submit"]), select, textarea')) return;
    const footer = form.querySelector(':scope > .form-actions');
    const tabs = form.querySelector(':scope > [role="tablist"]');
    const fields = form.ownerDocument.createElement('div');
    fields.className = 'workspace-panel-fields';
    [...form.childNodes].forEach(node => { if (node !== footer && node !== tabs) fields.append(node); });
    if (tabs) form.append(tabs);
    form.append(fields);
    if (footer) form.append(footer);
    form.classList.add('workspace-panel-form');
  };
  const upgrade = () => {
    document.querySelectorAll('dialog.modal-dialog').forEach(dialog => {
      if (dialog.classList.contains('workspace-remote-drawer')) return;
      const forms = [...dialog.querySelectorAll('form')].filter(form => form.querySelector('input:not([type="hidden"]):not([type="submit"]),select,textarea'));
      if (!forms.length && !dialog.hasAttribute('data-appointment-drawer')) return;
      dialog.classList.add('workspace-drawer');
      forms.forEach(wrapForm);
    });
  };
  upgrade();
  new MutationObserver(upgrade).observe(document.body, {childList:true,subtree:true});
  // Child editors run their own original scripts; never create nested remote editors.
  if (window.self !== window.top) return;
  const remote = document.createElement('dialog');
  remote.className = 'modal-dialog workspace-drawer workspace-remote-drawer';
  remote.setAttribute('aria-labelledby','workspace-remote-title');
  const card = document.createElement('div'); card.className = 'modal-card';
  const header = document.createElement('header'); header.className = 'modal-head workspace-remote-header';
  const title = document.createElement('h2'); title.id = 'workspace-remote-title'; title.className = 'workspace-remote-title';
  const utilities = document.createElement('div'); utilities.className = 'workspace-remote-utilities';
  const fullPage = document.createElement('a'); fullPage.textContent = 'Open full page'; fullPage.target = '_blank'; fullPage.rel = 'noopener';
  const close = document.createElement('button'); close.type = 'button'; close.className = 'modal-close'; close.textContent = '×'; close.setAttribute('aria-label','Close editor');
  const loading = document.createElement('p'); loading.className = 'workspace-loading'; loading.setAttribute('role','status'); loading.textContent = 'Loading…';
  const unsaved = document.createElement('div'); unsaved.className = 'workspace-unsaved'; unsaved.hidden = true; unsaved.setAttribute('role','alert');
  const unsavedText = document.createElement('p'); unsavedText.textContent = 'You have unsaved changes.';
  const keepEditing = document.createElement('button'); keepEditing.type = 'button'; keepEditing.className = 'btn btn-secondary'; keepEditing.textContent = 'Keep editing';
  const discard = document.createElement('button'); discard.type = 'button'; discard.className = 'btn btn-secondary'; discard.textContent = 'Discard changes';
  unsaved.append(unsavedText,keepEditing,discard);
  const frame = document.createElement('iframe'); frame.title = 'Create or edit record'; frame.referrerPolicy = 'same-origin';
  utilities.append(fullPage,close); header.append(title,utilities); card.append(header,unsaved,loading,frame); remote.append(card); document.body.append(remote);
  let dirty = false, submitting = false, source = null, opener = null, returnToInbox = false;
  const safeURL = value => {
    const url = new URL(value,location.href);
    if (url.origin !== location.origin || url.username || url.password) return null;
    return url;
  };
  const canClose = () => {
    if (submitting) return false;
    if (!dirty) return true;
    unsaved.hidden = false; keepEditing.focus(); return false;
  };
  keepEditing.addEventListener('click',() => { unsaved.hidden = true; frame.focus(); });
  discard.addEventListener('click',() => { dirty = false; unsaved.hidden = true; remote.close(); });
  const closeEditor = () => { if (canClose()) remote.close(); };
  close.addEventListener('click',closeEditor);
  remote.addEventListener('cancel',event => { if (!canClose()) event.preventDefault(); });
  remote.addEventListener('click',event => {
    if (event.target === remote) { event.preventDefault(); event.stopPropagation(); closeEditor(); }
  });
  remote.addEventListener('close',() => {
    frame.removeAttribute('src'); frame.style.visibility = 'hidden'; dirty = false; submitting = false;
    close.disabled = false; opener?.focus(); opener = null; source = null; returnToInbox = false;
    unsaved.hidden = true;
  });
  window.addEventListener('beforeunload',event => { if (remote.open && dirty && !submitting) event.preventDefault(); });
  const leaveEditor = target => {
    const url = safeURL(target);
    if (!url) return;
    url.searchParams.delete('_workspace_drawer');
    dirty = false; submitting = false;
    window.location.assign(url.href);
  };
  frame.addEventListener('load',async () => {
    if (!remote.open || !source) return;
    let doc;
    try { doc = frame.contentDocument; } catch (_) { doc = null; }
    if (!doc?.body) { leaveEditor(source.href); return; }
    const redirect = doc.body.dataset.workspaceDrawerRedirect;
    if (redirect) {
      const destination = safeURL(redirect);
      if (!destination) return;
      if (returnToInbox && doc.body.dataset.workspaceDrawerResult === 'complete') {
        dirty = false; submitting = false; remote.close();
        // Reload the existing URL, including its type/page filter. Browser scroll restoration
        // keeps the list position without storing patient identifiers or drafts in storage.
        window.location.reload();
      } else if (returnToInbox && doc.body.dataset.workspaceDrawerResult === 'retry') {
        const retry = new URL(source.href); retry.searchParams.set('_workspace_drawer','1');
        frame.src = retry.href;
      } else { leaveEditor(destination.href); }
      return;
    }
    let current;
    try { current = safeURL(frame.contentWindow.location.href); } catch (_) { current = null; }
    if (!current || current.pathname !== source.pathname) { leaveEditor(current?.href || source.href); return; }
    const main = doc.querySelector('main.app-main');
    const reviewMode = Boolean(main?.hasAttribute?.('data-workspace-review'));
    const forms = [...(main?.querySelectorAll('form') || [])].filter(form => !form.closest('dialog,.action-bar,.profile-menu') &&
      form.querySelector('input:not([type="hidden"]):not([type="submit"]),select,textarea'));
    if (!main || (!forms.length && !reviewMode)) { leaveEditor(current.href); return; }
    doc.documentElement.classList.add('workspace-drawer-frame');
    if (reviewMode) doc.documentElement.classList.add('workspace-review-frame');
    const heading = main.querySelector('.panel h1,.panel h2,.form-panel h1,.form-panel h2') || main.querySelector('h1');
    if (heading) { title.textContent = heading.textContent.trim(); heading.classList.add('sr-only'); }
    if (!reviewMode) forms.forEach(form => {
      const panel = form.closest('.panel,.form-panel,.intake-form-panel');
      if (panel) panel.classList.add('workspace-frame-card');
      wrapForm(form);
    });
    if (reviewMode) main.querySelectorAll('form').forEach(form => {
      // A submit button named "action" shadows form.action (HTML named properties).
      const action = safeURL(new URL(form.getAttribute('action') || current.href, current.href).href);
      if (action) {
        action.searchParams.set('_workspace_drawer','1');
        form.setAttribute('action',action.href);
      }
    });
    const addStyle = href => new Promise(resolve => {
      const link = doc.createElement('link'); link.rel = 'stylesheet'; link.href = new URL(href,location.href).href;
      link.onload = resolve; link.onerror = resolve; doc.head.append(link);
    });
    await Promise.all([addStyle(config.dataset.baseStyle),addStyle(config.dataset.drawerStyle)]);
    if (!remote.open) return;
    dirty = !reviewMode && Boolean(main.querySelector('.errorlist,.form-error:not([hidden])'));
    submitting = false; close.disabled = false;
    for (const eventName of ['input','change']) doc.addEventListener(eventName,() => { dirty = true; },true);
    doc.addEventListener('submit',event => {
      if (event.defaultPrevented || !main.contains(event.target)) return;
      submitting = true; dirty = false; close.disabled = true;
    });
    doc.addEventListener('click',event => {
      if (event.target.closest('[data-intake-builder] button')) dirty = true;
      const link = event.target.closest('a[href]');
      if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
      const destination = safeURL(link.href);
      if (!destination) return;
      if (/^(cancel|back(?: to)?\b)/i.test(link.textContent.trim())) {
        event.preventDefault(); closeEditor();
      } else if (destination.pathname !== source.pathname) {
        event.preventDefault(); if (canClose()) leaveEditor(destination.href);
      }
    });
    loading.hidden = true; frame.style.visibility = 'visible';
    const focus = main.querySelector('.form-error[tabindex],.errorlist,input:not([type="hidden"]),select,textarea');
    focus?.focus();
  });
  document.addEventListener('click',event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const native = link.dataset.modalTarget && document.getElementById(link.dataset.modalTarget);
    if (native) { upgrade(); return; }
    const url = safeURL(link.href);
    const editorPaths = [
      /^\/clients\/(?:new|\d+\/edit)\/$/,
      /^\/appointments\/(?:new|\d+\/edit|events\/(?:new|\d+\/edit)|availability(?:\/\d+\/edit)?)\/$/,
      /^\/clinical-notes\/(?:new|\d+\/edit|diagnoses\/(?:new|\d+\/edit)|treatment-plans\/(?:new|\d+\/edit))\/$/,
      /^\/billing\/(?:invoices\/(?:new|\d+\/edit)|packages\/(?:new|\d+\/edit)|payments\/new|usage\/new)\/$/,
      /^\/documents\/new\/$/,
      /^\/intake\/templates\/(?:new|\d+\/edit)\/$/,
      /^\/intake\/measures\/new\/$/,
      /^\/settings\/(?:session-packages|insurance\/payers|insurance\/rates|client-portal)\/(?:new|\d+\/edit)\/$/,
      /^\/settings\/availability\/new\/$/,
    ];
    const reviewPaths = [
      /^\/intake\/\d+\/responses\/$/,
      /^\/clients\/\d+\/information\/\d+\/$/,
      /^\/inbox\/(?:portal|booking|note)\/\d+\/$/,
    ];
    if (!url || !(editorPaths.some(pattern => pattern.test(url.pathname)) ||
        (link.dataset.workspaceReview === '1' && reviewPaths.some(pattern => pattern.test(url.pathname))))) return;
    if (typeof remote.showModal !== 'function') return;
    event.preventDefault(); event.stopImmediatePropagation();
    source = url; opener = link; dirty = false; submitting = false;
    returnToInbox = location.pathname === '/inbox/' && link.dataset.workspaceReturn === 'refresh';
    title.textContent = link.textContent.trim() || 'Create or edit';
    fullPage.href = url.href; close.disabled = false; loading.hidden = false; frame.style.visibility = 'hidden';
    const embedded = new URL(url.href); embedded.searchParams.set('_workspace_drawer','1');
    frame.src = embedded.href; remote.showModal(); close.focus();
  },true);
})();
