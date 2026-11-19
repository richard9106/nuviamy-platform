    const calendarGridConfig = JSON.parse(document.getElementById('calendar-grid-config')?.textContent || '{"startHour":7,"endHour":20,"hourHeight":72,"defaultDurationMinutes":50}');
    let draggedAppointment = null;

    function timeFromPointer(event, target) {
      const rect = target.getBoundingClientRect();
      const headerHeight = target.querySelector('.gcal-day-head')?.getBoundingClientRect().height || 64;
      const y = Math.max(0, event.clientY - rect.top - headerHeight);
      const rawMinutes = Math.round((y / calendarGridConfig.hourHeight) * 60);
      const roundedMinutes = Math.max(0, Math.round(rawMinutes / 15) * 15);
      const totalMinutes = calendarGridConfig.startHour * 60 + roundedMinutes;
      const hours = Math.min(calendarGridConfig.endHour, Math.floor(totalMinutes / 60));
      const minutes = hours === calendarGridConfig.endHour ? 0 : totalMinutes % 60;
      return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    }

    function datetimeFor(dateValue, timeValue, durationMinutes = calendarGridConfig.defaultDurationMinutes) {
      const [hours, minutes] = timeValue.split(':').map(Number);
      const start = new Date(`${dateValue}T00:00:00`);
      start.setHours(hours, minutes, 0, 0);
      const end = new Date(start.getTime() + durationMinutes * 60000);
      const format = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}T${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`;
      return { start: format(start), end: format(end) };
    }

    function minutesFor(timeValue) {
      const [hours, minutes] = timeValue.split(':').map(Number);
      return hours * 60 + minutes;
    }

    function isAvailable(column, timeValue, durationMinutes = calendarGridConfig.defaultDurationMinutes) {
      if (column.dataset.availabilityConfigured !== '1') return true;
      const start = minutesFor(timeValue);
      const end = start + durationMinutes;
      return (column.dataset.availabilityRanges || '').split(';').filter(Boolean).some((range) => {
        const [rangeStart, rangeEnd] = range.split('-').map(Number);
        return rangeStart <= start && rangeEnd >= end;
      });
    }

    document.addEventListener('click', (event) => {
      if (!event.target.closest('[data-availability-review]')) return;
      event.preventDefault();
      const panel = document.getElementById('availability-changes');
      panel.open = true;
      panel.querySelector('summary').focus();
      panel.scrollIntoView({ block: 'start' });
    });

    let movePending = false;
    let dragPreview = null;
    const moveNotice = (message, needsRefresh = false) => {
      const feedback = document.querySelector('[data-calendar-move-feedback]');
      if (!feedback) return;
      feedback.hidden = false;
      feedback.querySelector('[data-calendar-move-message]').textContent = message;
      feedback.querySelector('[data-calendar-refresh]').hidden = !needsRefresh;
    };
    const clearDragPreview = () => {
      dragPreview?.remove(); dragPreview = null;
      document.querySelectorAll('.drop-ready').forEach(column => column.classList.remove('drop-ready'));
    };
    const showDragPreview = (event, target) => {
      if (!draggedAppointment || !target.classList.contains('gcal-day-column')) return;
      const time = timeFromPointer({clientY: event.clientY - draggedAppointment.pointerOffset}, target);
      if (!dragPreview) {
        dragPreview = document.createElement('div');
        dragPreview.className = 'gcal-event calendar-drag-preview';
        dragPreview.setAttribute('aria-hidden', 'true');
        const title = document.createElement('strong'); title.textContent = draggedAppointment.title;
        dragPreview.append(title, document.createElement('span'));
      }
      target.append(dragPreview);
      const top = (minutesFor(time) - calendarGridConfig.startHour * 60) * calendarGridConfig.hourHeight / 60;
      dragPreview.style.top = `${top}px`;
      dragPreview.style.height = `${Math.max(20, draggedAppointment.duration * calendarGridConfig.hourHeight / 60)}px`;
      dragPreview.querySelector('span').textContent = `${time} · ${draggedAppointment.duration} min`;
      dragPreview.classList.toggle('drop-unavailable', !isAvailable(target, time, draggedAppointment.duration));
    };
    document.addEventListener('dragstart', event => {
      const item = event.target.closest('[data-draggable-appointment]');
      if (!item) return;
      if (movePending) { event.preventDefault(); return; }
      draggedAppointment = {
        title: item.dataset.appointmentTitle,
        time: item.dataset.appointmentTime,
        duration: Number(item.dataset.appointmentDuration) || calendarGridConfig.defaultDurationMinutes,
        url: item.dataset.rescheduleUrl,
        pointerOffset: item.getBoundingClientRect ? Math.max(0, event.clientY - item.getBoundingClientRect().top) : 0,
        expectedStart: item.dataset.startsAt,
        expectedEnd: item.dataset.endsAt,
        trigger: item,
      };
      item.classList.add('calendar-drag-source');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', 'NuviaMy appointment');
    });
    document.addEventListener('dragover', event => {
      const target = event.target.closest('[data-drop-date]');
      if (!target || !draggedAppointment) return;
      event.preventDefault(); event.dataTransfer.dropEffect = 'move';
      document.querySelectorAll('.drop-ready').forEach(column => { if (column !== target) column.classList.remove('drop-ready'); });
      target.classList.add('drop-ready');
      showDragPreview(event, target);
    });
    document.addEventListener('dragleave', event => {
      const target = event.target.closest('[data-drop-date]');
      if (target && !target.contains(event.relatedTarget)) target.classList.remove('drop-ready');
    });
    document.addEventListener('dragend', () => {
      draggedAppointment?.trigger.classList.remove('calendar-drag-source');
      draggedAppointment = null;
      if (!movePending) clearDragPreview();
    });
    document.addEventListener('drop', async event => {
      const target = event.target.closest('[data-drop-date]');
      if (!target || !draggedAppointment) return;
      event.preventDefault();
      const moving = draggedAppointment; draggedAppointment = null;
      const time = target.classList.contains('gcal-day-column') ? timeFromPointer({clientY: event.clientY - moving.pointerOffset}, target) : moving.time || '09:00';
      if (target.classList.contains('gcal-day-column') && !isAvailable(target, time, moving.duration)) {
        moving.trigger.classList.remove('calendar-drag-source'); clearDragPreview();
        moveNotice('This time is outside practice availability. The appointment has not moved.'); return;
      }
      if (target.dataset.dropDate === moving.expectedStart?.slice(0, 10) && time === moving.time) {
        moving.trigger.classList.remove('calendar-drag-source'); clearDragPreview(); return;
      }
      movePending = true;
      document.querySelector('.calendar-panel')?.setAttribute('aria-busy', 'true');
      moveNotice('Saving appointment…');
      let saved = false;
      try {
        const response = await fetch(moving.url, {
          method: 'POST', credentials: 'same-origin', redirect: 'error',
          headers: {'X-CSRFToken': document.querySelector('[name="csrfmiddlewaretoken"]').value, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
          body: new URLSearchParams({date: target.dataset.dropDate, time, expected_starts_at: moving.expectedStart, expected_ends_at: moving.expectedEnd}),
        });
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('unconfirmed');
        const result = await response.json();
        if (!response.ok || !result.ok) { moveNotice(result.message || 'The appointment could not be moved.', response.status === 409); return; }
        saved = true;
        const editor = document.getElementById(moving.trigger.dataset.modalTarget);
        if (editor) {
          editor.querySelector('[name="starts_at"]').value = result.starts_at.slice(0, 16);
          editor.querySelector('[name="ends_at"]').value = result.ends_at.slice(0, 16);
          editor.querySelector('[data-reschedule-date]')?.setAttribute('data-reschedule-date', result.starts_at.slice(0, 10));
          editor.querySelector('[data-reschedule-time]')?.setAttribute('data-reschedule-time', result.starts_at.slice(11, 16));
        }
        const page = await fetch(window.location.href, {credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
        if (!page.ok) throw new Error('refresh');
        const updated = new DOMParser().parseFromString(await page.text(), 'text/html');
        const panel = updated.querySelector('.calendar-panel');
        if (!panel) throw new Error('refresh');
        document.querySelector('.calendar-panel').replaceWith(panel);
        const updatedEditor = editor && updated.getElementById(editor.id);
        if (updatedEditor) ['.session-records .panel', '.sync-panel'].forEach(selector => {
          const fresh = updatedEditor.querySelector(selector), old = editor.querySelector(selector);
          if (fresh && old) old.replaceWith(fresh);
        });
        document.dispatchEvent(new Event('calendar:updated'));
        moveNotice(result.sync_failed ? 'Appointment moved. Google Calendar sync needs attention.' : 'Appointment moved successfully.');
      } catch (_) {
        moveNotice(saved ? 'Appointment saved. Refresh the calendar to see its latest position.' : 'Could not confirm the move. Refresh the calendar before trying again.', true);
      } finally {
        movePending = false; moving.trigger.classList.remove('calendar-drag-source'); clearDragPreview();
        document.querySelector('.calendar-panel')?.removeAttribute('aria-busy');
      }
    });
    document.addEventListener('click', event => {
      if (event.target.closest('[data-calendar-refresh]')) window.location.reload();
    });

    document.addEventListener('click', (event) => {
      const column = event.target.closest('.gcal-day-column[data-drop-date]');
      if (!column || event.target.closest('a, button, input, select, textarea')) return;
      const dialog = document.getElementById('appointment-create-modal');
      if (!dialog || typeof dialog.showModal !== 'function') return;
      const selectedTime = timeFromPointer(event, column);
      const duration = dialog.querySelector('[name="session_kind"]')?.value === 'initial_consultation' ? 15 : calendarGridConfig.defaultDurationMinutes;
      const values = datetimeFor(column.dataset.dropDate, selectedTime, duration);
      const feedback = dialog.querySelector('[data-scheduling-feedback]');
      if (feedback) feedback.hidden = isAvailable(column, selectedTime, duration);
      dialog.querySelector('[name="starts_at"]').value = values.start;
      dialog.querySelector('[name="ends_at"]').value = values.end;
      dialog._returnFocus = column.querySelector('[data-modal-target="appointment-create-modal"]');
      dialog.showModal();
      dialog.querySelector('[name="client"]')?.focus();
    });

    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-modal-target]');
      if (!trigger) return;
      const dialog = document.getElementById(trigger.dataset.modalTarget);
      if (!dialog || typeof dialog.showModal !== 'function') return;
      event.preventDefault();
      const feedback = dialog.querySelector('[data-scheduling-feedback]');
      if (feedback) feedback.hidden = true;
      if (trigger.dataset.appointmentDate) {
        const start = dialog.querySelector('[name="starts_at"]');
        const end = dialog.querySelector('[name="ends_at"]');
        start.value = `${trigger.dataset.appointmentDate}T09:00`;
        end.value = `${trigger.dataset.appointmentDate}T${dialog.querySelector('[name="session_kind"]')?.value === 'initial_consultation' ? '09:15' : '09:50'}`;
      }
      if (trigger.dataset.availabilityDate && dialog.id === 'availability-modal') {
        dialog.querySelector('[name="date"]').value = trigger.dataset.availabilityDate;
        dialog.querySelector('[name="starts_at"]').value = '09:00';
        dialog.querySelector('[name="ends_at"]').value = '17:00';
        dialog.querySelector('[name="end_date"]').value = '';
        dialog.querySelector('[name="is_available"]').checked = true;
        dialog.querySelector('[data-availability-prompt]').hidden = true;
      }
    }, true);
    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-modal-close]');
      if (trigger) trigger.closest('dialog')?.close();
    });

    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('button[data-reschedule-url]');
      if (!trigger) return;
      const dialog = document.getElementById('reschedule-modal');
      const form = dialog?.querySelector('[data-reschedule-form]');
      if (!form) return;
      const sessionDialog = trigger.closest('dialog');
      sessionDialog?.close();
      const feedback = dialog.querySelector('[data-scheduling-feedback]');
      if (feedback) feedback.hidden = true;
      form.action = trigger.dataset.rescheduleUrl;
      form.elements.date.value = trigger.dataset.rescheduleDate;
      form.elements.time.value = trigger.dataset.rescheduleTime;
      form.elements.next.value = window.location.pathname + window.location.search;
      dialog.querySelector('[data-reschedule-title]').textContent = `Move ${trigger.dataset.rescheduleTitle || 'appointment'}`;
      dialog._returnFocus = document.querySelector(`[data-modal-target="appointment-modal-${sessionDialog?.id.replace('appointment-modal-', '')}"]`) || trigger;
      dialog.showModal();
      form.elements.date.focus();
    });

    document.querySelectorAll('form.appointment-form').forEach((form) => {
      if (form.querySelector('[name="session_kind"]')) return;
      const start = form.querySelector('[name="starts_at"]');
      const end = form.querySelector('[name="ends_at"]');
      if (!start || !end || start.type === 'time' || end.type === 'time') return;
      const duration = () => (new Date(end.value) - new Date(start.value)) / 60000;
      let minutes = duration() > 0 ? duration() : calendarGridConfig.defaultDurationMinutes;
      start.addEventListener('focus', () => { if (duration() > 0) minutes = duration(); });
      end.addEventListener('change', () => { if (duration() > 0) minutes = duration(); });
      start.addEventListener('change', () => {
        if (!start.value) return;
        const values = datetimeFor(start.value.slice(0, 10), start.value.slice(11), minutes);
        end.value = values.end;
      });
    });

    document.querySelector('[data-edit-reschedule]')?.addEventListener('click', () => {
      const start = document.querySelector('#appointment-form [name="starts_at"]');
      start?.focus();
      start?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
