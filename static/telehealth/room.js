(() => {
  'use strict';
  const root = document.getElementById('video-app');
  if (!root) return;
  const el = id => document.getElementById(id);
  const role = root.dataset.role;
  const nonce = crypto.randomUUID();
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  let preview = null, session = null, controller = null;
  let devicesReady = false, hasCamera = true, joined = false, waiting = false;
  let connecting = false, polling = false, failures = 0, timer = null, expiryTimer = null;
  let microphoneMuted = false, cameraMuted = false, leaving = false, testing = false;
  const silentLogger = {info() {}, warn() {}, error() {}, debug() {}, setLogLevel() {}, getLogLevel() { return 4; }};
  const silentEvents = {addObserver() {}, removeObserver() {}, async publishEvent() {}};
  function status(text) { el('video-status').textContent = text; }
  function notice(text) { el('video-notice').textContent = text; el('video-notice').hidden = !text; }
  function stopPreview() {
    if (preview) preview.getTracks().forEach(track => track.stop());
    preview = null; el('local-video').srcObject = null;
  }
  async function post(action, keepalive = false) {
    const response = await fetch(root.dataset.api, {method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf},
      body: JSON.stringify({action, nonce}), keepalive});
    if (!response.ok || response.redirected) throw new Error('unavailable');
    return response.json();
  }
  async function testDevices(audioOnly = false) {
    if (joined || waiting || connecting || testing || leaving) return;
    testing = true;
    el('test-devices').disabled = true; el('audio-only').disabled = true;
    notice(''); stopPreview();
    el('join-session').disabled = true; devicesReady = false;
    try {
      preview = await navigator.mediaDevices.getUserMedia({audio: true, video: !audioOnly});
      if (leaving) { stopPreview(); return; }
      hasCamera = preview.getVideoTracks().length > 0;
      el('toggle-camera').disabled = !hasCamera;
      el('local-video').srcObject = preview; el('local-video').hidden = !hasCamera;
      el('local-video').classList.add('preview-large');
      const devices = await navigator.mediaDevices.enumerateDevices();
      for (const [id, kind] of [['microphone', 'audioinput'], ['camera', 'videoinput']]) {
        const select = el(id); select.replaceChildren();
        devices.filter(device => device.kind === kind).forEach((device, i) => {
          const option = document.createElement('option'); option.value = device.deviceId;
          option.textContent = device.label || `${id} ${i + 1}`; select.appendChild(option);
        });
        select.disabled = !select.options.length || (id === 'camera' && !hasCamera);
      }
      devicesReady = true; el('join-session').disabled = false;
      status(hasCamera ? 'Camera and microphone are ready.' : 'Microphone ready · audio only.');
      el('device-note').textContent = 'Preview only. Your camera and microphone are not connected to the session yet.';
    } catch (_) {
      stopPreview(); notice('We couldn’t access your devices. Check browser permissions, or try microphone only.');
      status('Check your device permissions.');
    } finally {
      testing = false; el('test-devices').disabled = false; el('audio-only').disabled = false;
    }
  }
  async function disconnect() {
    stopPreview(); joined = false; waiting = false;
    clearInterval(timer); timer = null; clearTimeout(expiryTimer); expiryTimer = null;
    if (session) {
      const current = session; session = null;
      try { current.audioVideo.stopLocalVideoTile(); current.audioVideo.stop();
        await current.audioVideo.stopVideoInput(); await current.audioVideo.stopAudioInput(); await current.destroy(); } catch (_) {}
    }
    if (controller) { try { await controller.destroy(); } catch (_) {} controller = null; }
    el('local-video').hidden = true; el('remote-video').hidden = true;
    el('remote-placeholder').hidden = false; el('waiting-client')?.setAttribute('hidden', '');
    el('connection-label').textContent = 'Not connected';
  }
  async function finish(text) {
    leaving = true; await disconnect();
    status(text); notice(text); el('call-controls').hidden = true; el('prejoin').hidden = true;
    el('stage-title').textContent = 'Your video room is closed.';
    el('stage-detail').textContent = 'Return to your portal or appointments for the next step.';
    el('stage-badge').textContent = 'Session closed';
  }
  function armExpiry(iso) {
    if (!iso) return;
    clearTimeout(expiryTimer);
    expiryTimer = setTimeout(() => { post(role === 'host' ? 'end' : 'leave').catch(() => {});
      finish('The video session has ended.'); }, Math.max(0, Date.parse(iso) - Date.now()));
  }
  async function connect(payload) {
    if (joined || connecting || leaving) return;
    connecting = true;
    try {
      const sdk = window.NuviaVideoSDK;
      if (!sdk) throw new Error('sdk_unavailable');
      const audioId = el('microphone').value, videoId = el('camera').value;
      stopPreview(); el('local-video').classList.remove('preview-large');
      controller = new sdk.DefaultDeviceController(silentLogger);
      const configuration = new sdk.MeetingSessionConfiguration(payload.Meeting, payload.Attendee);
      // Avoid optional event-ingestion telemetry; only session media/signaling is used.
      configuration.urls.eventIngestionURL = null;
      session = new sdk.DefaultMeetingSession(configuration, silentLogger, controller, silentEvents);
      session.audioVideo.addObserver({
        audioVideoDidStart() { status('You’re in the session.'); el('connection-label').textContent = 'Connected'; },
        audioVideoDidStartConnecting(reconnecting) { if (reconnecting) status('Reconnecting…'); },
        audioVideoDidStop() { if (!leaving) finish('The video connection ended. Return to your appointments or contact your practice.'); },
        videoTileDidUpdate(tile) {
          if (!tile.boundAttendeeId || tile.isContent) return;
          const video = el(tile.localTile ? 'local-video' : 'remote-video');
          session?.audioVideo.bindVideoElement(tile.tileId, video); video.hidden = false;
          if (!tile.localTile) el('remote-placeholder').hidden = true;
        },
        videoTileWasRemoved() {
          if (session && !session.audioVideo.getAllRemoteVideoTiles().length) {
            el('remote-video').hidden = true; el('remote-placeholder').hidden = false;
          }
        }
      });
      await session.audioVideo.startAudioInput(audioId || null);
      if (hasCamera && !cameraMuted) await session.audioVideo.startVideoInput(videoId);
      await session.audioVideo.bindAudioElement(el('remote-audio'));
      if (microphoneMuted) session.audioVideo.realtimeMuteLocalAudio();
      session.audioVideo.start(); if (hasCamera && !cameraMuted) session.audioVideo.startLocalVideoTile();
      joined = true; waiting = false;
      el('toggle-camera').disabled = !hasCamera;
      el('stage-title').textContent = 'Waiting for the other participant.';
      el('stage-detail').textContent = role === 'host' ? 'Your client will appear here after you admit them.' : 'Your therapist’s video will appear here.';
      el('stage-badge').textContent = 'Private session';
      el('waiting-note')?.setAttribute('hidden', '');
      el('remote-audio').play().catch(() => { el('enable-sound').hidden = false; });
      armExpiry(payload.expiresAt);
    } catch (_) {
      post('leave').catch(() => {});
      await finish('We couldn’t connect the session. Check your devices and contact your practice if you need help.');
    } finally { connecting = false; }
  }
  async function enter() {
    if (!devicesReady || connecting || joined || waiting || leaving) return;
    el('join-session').disabled = true; notice('');
    try {
      const result = await post('join');
      if (result.state === 'retry') {
        el('join-session').disabled = false; status('Please try joining again in a moment.'); return;
      }
      if (['ended', 'unavailable', 'superseded'].includes(result.state)) {
        await finish('This session is not open. Check the appointment time or contact your practice.'); return;
      }
      el('prejoin').hidden = true; el('call-controls').hidden = false;
      if (result.state === 'joined') await connect(result);
      else {
        waiting = true; status('You’re in the waiting room.');
        el('stage-badge').textContent = 'Waiting room · private preview';
        el('stage-title').textContent = 'Your therapist will be with you shortly.';
        el('stage-detail').textContent = 'Your camera and microphone are not being shared while you wait.';
      }
      if (!leaving) timer = setInterval(poll, 5000);
    } catch (_) {
      el('join-session').disabled = false;
      notice('Video is temporarily unavailable. Please try again shortly or contact your practice.');
    }
  }
  async function poll() {
    if (polling || leaving) return; polling = true;
    try {
      const result = await post('heartbeat'); failures = 0;
      if (['ended', 'unavailable', 'superseded', 'left'].includes(result.state)) {
        await finish('This video session is no longer available.'); return;
      }
      if (role === 'host') el('waiting-client').hidden = !result.waiting;
      if (role === 'patient' && waiting && result.state === 'admitted' && !connecting) {
        const payload = await post('join');
        if (payload.state === 'joined') await connect(payload);
        else if (payload.state !== 'retry') await finish('This video session is no longer available.');
      }
      armExpiry(result.expiresAt);
    } catch (_) {
      failures += 1; status('Checking your connection…');
      if (failures >= 2) await finish('We lost the secure session connection. Sign in again or contact your practice.');
    } finally { polling = false; }
  }
  el('test-devices').addEventListener('click', () => testDevices());
  el('audio-only').addEventListener('click', () => testDevices(true));
  el('join-session').addEventListener('click', enter);
  el('leave-session').addEventListener('click', async () => {
    leaving = true; post('leave').catch(() => {}); await finish('You’ve left the video room.');
  });
  el('end-session')?.addEventListener('click', async () => {
    leaving = true; try { await post('end'); } catch (_) { notice('The room will close automatically. Contact support if needed.'); }
    await finish('You’ve ended this session.');
  });
  el('admit-client')?.addEventListener('click', async () => {
    el('admit-client').disabled = true;
    try { await post('admit'); el('waiting-client').hidden = true; status('Client admitted.'); }
    catch (_) { notice('Couldn’t admit the client. Please try again.'); }
    finally { el('admit-client').disabled = false; }
  });
  el('toggle-mic').addEventListener('click', () => {
    microphoneMuted = !microphoneMuted;
    if (session) microphoneMuted ? session.audioVideo.realtimeMuteLocalAudio() : session.audioVideo.realtimeUnmuteLocalAudio();
    preview?.getAudioTracks().forEach(track => { track.enabled = !microphoneMuted; });
    el('toggle-mic').textContent = microphoneMuted ? 'Unmute microphone' : 'Mute microphone';
    el('toggle-mic').setAttribute('aria-pressed', String(microphoneMuted));
  });
  el('toggle-camera').addEventListener('click', async () => {
    cameraMuted = !cameraMuted;
    if (session) {
      try {
        if (cameraMuted) { session.audioVideo.stopLocalVideoTile(); await session.audioVideo.stopVideoInput(); }
        else { await session.audioVideo.startVideoInput(el('camera').value); session.audioVideo.startLocalVideoTile(); }
      } catch (_) { cameraMuted = true; notice('We couldn’t enable the camera. Your microphone can still be used.'); }
    }
    preview?.getVideoTracks().forEach(track => { track.enabled = !cameraMuted; });
    el('local-video').hidden = cameraMuted;
    el('toggle-camera').textContent = cameraMuted ? 'Turn camera on' : 'Turn camera off';
    el('toggle-camera').setAttribute('aria-pressed', String(cameraMuted));
  });
  el('enable-sound').addEventListener('click', () => { el('remote-audio').play().then(() => { el('enable-sound').hidden = true; }).catch(() => notice('Check your browser sound permissions.')); });
  window.addEventListener('pagehide', () => {
    if (joined || waiting) post('leave', true).catch(() => {});
    leaving = true; disconnect();
  });
})();
