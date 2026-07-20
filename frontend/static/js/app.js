/* SmartCrowd safety operations dashboard. */
(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const delay = (milliseconds) => new Promise(resolve => window.setTimeout(resolve, milliseconds));
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[character]));
  const formatNumber = (value) => Number(value || 0).toLocaleString();
  const formatRuntime = (seconds = 0) => [
    Math.floor(seconds / 3600),
    Math.floor((seconds % 3600) / 60),
    seconds % 60,
  ].map(value => String(value).padStart(2, '0')).join(':');
  const formatDate = (value) => value ? new Date(value).toLocaleString() : '-';
  const formatRange = (range) => ({
    '5m': 'Last 5 minutes', '15m': 'Last 15 minutes', '30m': 'Last 30 minutes',
    '1h': 'Last 1 hour', '6h': 'Last 6 hours', '12h': 'Last 12 hours',
    '24h': 'Last 24 hours', '7d': 'Last 7 days', custom: 'Custom range',
  }[range] || 'Selected range');

  class ApiClient {
    async request(url, options = {}) {
      const headers = { ...(options.headers || {}) };
      if (options.body && !(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
      let response;
      try {
        response = await fetch(url, { ...options, headers });
      } catch (_) {
        throw new Error('Unable to reach the local SmartCrowd backend.');
      }
      let payload;
      try {
        payload = await response.json();
      } catch (_) {
        throw new Error(`The server returned an unexpected response (${response.status}).`);
      }
      if (!response.ok || !payload.success) {
        const code = payload.details?.code;
        const friendly = {
          camera_busy: 'Camera is already in use by another application.',
          camera_not_found: 'Camera was not found. Check the connection and selected device.',
          permission_denied: 'Camera permission was denied. Enable permission or upload a video.',
          stream_unavailable: 'The camera stream is unavailable. Check the URL and network connection.',
        }[code];
        const error = new Error(friendly || payload.message || `Request failed (${response.status}).`);
        error.details = payload.data || payload.details;
        throw error;
      }
      return payload.data;
    }

    async initialize() {
      try {
        const response = await fetch('/api/system/initialize', { method: 'POST' });
        const payload = await response.json();
        if (payload.data) return payload.data;
      } catch (_) {
        // A diagnostic object lets the interface recover without exposing a raw transport failure.
      }
      return {
        ready: false,
        status: 'unhealthy',
        components: [{
          id: 'backend', title: 'Backend service', ready: false, status: 'critical',
          detail: 'The local Flask service could not be reached or initialized.',
        }],
      };
    }

    async health() {
      try {
        const response = await fetch('/api/health');
        const payload = await response.json();
        if (payload.data) return payload.data;
      } catch (_) {
        // Fall through to a diagnostic-safe response.
      }
      return {
        ready: false,
        components: [{ id: 'backend', title: 'Backend service', ready: false, detail: 'Backend health check is unavailable.' }],
      };
    }
  }

  class DashboardApp {
    constructor() {
      this.api = new ApiClient();
      this.state = {
        accepted: false,
        activePage: 'home',
        cameraId: null,
        cameras: [],
        settings: {},
        health: null,
        mode: 'live',
        feedKey: '',
        liveChart: null,
        historyChart: null,
        latestHistory: [],
        selectedRange: '1h',
        pollTimer: null,
        pollInFlight: false,
        pollCount: 0,
        busyCount: 0,
        knownAlerts: new Set(),
        shownErrors: new Set(), cameraPermission: 'unknown',
      };
    }

    async boot() {
      this.registerZoomPlugin();
      this.restoreSidebar();
      this.bindEvents();
      const health = await this.runStartupSequence();
      if (!health.ready) {
        this.showDiagnostics(health);
        return;
      }
      this.state.health = health;
      this.hideStartup();
      if (sessionStorage.getItem("scmConsentAccepted") === "true") {

        this.state.accepted = true;
        document.body.classList.remove('booting');
        document.body.classList.add('app-ready');
        $('#appRoot').setAttribute('aria-hidden', 'false');
        await this.initializeDashboard();

      } 
      else 
      {

        this.showConsent();

      }


    }

    registerZoomPlugin() {
      if (window.Chart && window.ChartZoom && !window.Chart.registry.plugins.get('zoom')) {
        window.Chart.register(window.ChartZoom);
      }
    }

    async runStartupSequence() {

        const steps = [
            'Initializing Smart Crowd Monitoring...',
            'Checking Backend Services...',
            'Checking Configuration...',
            'Loading AI Engine...',
            'Loading YOLOv8 Model...',
            'Loading ByteTrack...',
            'Loading Detection Engine...',
            'Loading Camera Services...',
            'Loading Reports Module...',
            'Loading Dashboard...',
            'Preparing User Interface...',
            'Finalizing Startup...Please Wait...'
        ];

        const initialization = this.api.initialize();

        for (const [index, step] of steps.entries()) {

            $('#startupStep').textContent = step;

            $('#startupDetail').textContent =
                index < 5
                    ? 'Verifying protected local components.'
                    : 'Building a reliable operating workspace.';

            $('#startupProgress').style.width =
                `${Math.round(((index + 1) / steps.length) * 100)}%`;

            await delay(80);

        }

        const health = await initialization;

        $('#startupStep').textContent =
            health.ready
                ? 'System Ready.'
                : 'Diagnostics found an issue.';

        $('#startupDetail').textContent =
            health.ready
                ? 'All required services have completed their checks.'
                : 'A required service needs attention before the dashboard can open.';

        /* ---------- Launch Animation ---------- */

        if (health.ready) {

            const shield = $('#startupShield');
            const overlay = $('#startupOverlay');

            shield.classList.add('launch');
            overlay.classList.add('fade-out');

            await delay(850);

        }

        return health;

    }

    hideStartup() {
      $('#startupOverlay').classList.add('complete');
      window.setTimeout(() => $('#startupOverlay').classList.add('d-none'), 360);
    }

    showDiagnostics(health) {
      $('#startupOverlay').classList.add('d-none');
      $('#diagnosticSummary').textContent = 'Resolve the critical checks below, then retry initialization.';
      $('#diagnosticList').innerHTML = (health.components || []).map(component => `
        <div class="diagnostic-row ${component.ready ? 'ready' : ''}">
          <i class="fa-solid ${component.ready ? 'fa-circle-check' : 'fa-circle-xmark'}"></i>
          <span><b>${escapeHtml(component.title)}</b><small>${escapeHtml(component.detail || 'No detail available.')}</small></span>
        </div>
      `).join('');
      $('#diagnosticOverlay').classList.remove('d-none');
    }

    showConsent() {
      $('#consentCard').classList.remove('d-none');
      $('#declineCard').classList.add('d-none');
      $('#consentOverlay').classList.remove('d-none');
    }

    async acceptConsent() {
      $('#consentOverlay').classList.add('d-none');
      sessionStorage.setItem("scmConsentAccepted", "true");
      this.state.accepted = true;
      document.body.classList.remove('booting');
      document.body.classList.add('app-ready');
      $('#appRoot').setAttribute('aria-hidden', 'false');
      await this.initializeDashboard();
    }

    declineConsent() {
      $('#consentCard').classList.add('d-none');
      $('#declineCard').classList.remove('d-none');
    }

    async initializeDashboard() {
      try {
        await this.withBusy('Loading workspace...', 'Synchronizing settings and operational data.', async () => {
          this.loadSettings(await this.api.request('/api/settings'));
          await this.refreshCameras(true);
          await this.loadLogs();
          this.renderHealth(this.state.health);
        });
        this.showPage(document.body.dataset.initialPage || 'home', false);
        this.bindFeed();
        await this.poll();
        this.startPolling();
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    async withBusy(title, detail, operation) {
      this.state.busyCount += 1;
      $('#operationTitle').textContent = title;
      $('#operationDetail').textContent = detail;
      $('#operationOverlay').classList.remove('d-none');
      try {
        return await operation();
      } finally {
        this.state.busyCount -= 1;
        if (!this.state.busyCount) $('#operationOverlay').classList.add('d-none');
      }
    }

    notify(message, tone = 'primary') {
      const id = `toast-${Date.now()}-${Math.round(Math.random() * 1000)}`;
      $('#toastContainer').insertAdjacentHTML('beforeend', `
        <div id="${id}" class="toast align-items-center text-bg-${tone}" role="alert">
          <div class="d-flex"><div class="toast-body">${escapeHtml(message)}</div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>
        </div>
      `);
      const element = $(`#${id}`);
      if (window.bootstrap) {
        const toast = new window.bootstrap.Toast(element, { delay: 4200 });
        element.addEventListener('hidden.bs.toast', () => element.remove());
        toast.show();
      } else {
        window.setTimeout(() => element.remove(), 4200);
      }
    }

    showPage(page, updateHistory = true) {
      const allowed = ['home', 'monitoring', 'analytics', 'reports', 'logs', 'settings', 'about','help'];
      const selected = allowed.includes(page) ? page : 'home';
      this.state.activePage = selected;
      $$('.page').forEach(element => element.classList.toggle('active', element.id === `${selected}Page`));
      $$('.main-nav a').forEach(link => link.classList.toggle('active', link.dataset.page === selected));
      const title = {
        home: ['Command center', 'SAFETY OPERATIONS'],
        monitoring: ['Live monitoring', 'CAMERA WORKSPACE'],
        analytics: ['Occupancy analytics', 'HISTORICAL INTELLIGENCE'],
        reports: ['Reports', 'EVIDENCE EXPORT'],
        logs: ['Event logs', 'AUDIT TRAIL'],
        settings: ['Settings', 'CONTROL PLANE'],
        about: ['About SmartCrowd', 'PROJECT INFORMATION'],
        help: ['Help Center', 'DOCUMENTATION & SUPPORT'],
      }[selected];
      $('#pageTitle').textContent = title[0];
      $('#pageEyebrow').textContent = title[1];
      if (updateHistory) history.pushState({ page: selected }, '', selected === 'home' ? '/' : `/${selected}`);
      $('#sidebar').classList.remove('mobile-open');
      if (selected === 'logs') this.loadLogs();
      if (selected === 'reports') this.loadReports();
      if (selected === 'analytics') this.loadAnalytics();
    }

    restoreSidebar() {
      if (localStorage.getItem('scm-sidebar-collapsed') === 'true') {
        document.body.classList.add('sidebar-collapsed');
      }
    }

    toggleSidebar() {
      document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('scm-sidebar-collapsed', String(document.body.classList.contains('sidebar-collapsed')));
    }

    applyTheme(theme, persist = false) {
      document.documentElement.dataset.theme = theme;
      $('#themeToggle i').className = theme === 'dark' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
      $('#themeSetting').value = theme;
      this.state.settings.theme = theme;
      if (persist) {
        this.api.request('/api/settings', { method: 'PUT', body: JSON.stringify({ theme }) })
          .catch(error => this.notify(error.message, 'danger'));
      }
    }

    loadSettings(settings) {
      this.state.settings = settings;
      $('#confidenceThreshold').value = settings.confidence_threshold;
      $('#confidenceOutput').textContent = `${Math.round(settings.confidence_threshold * 100)}%`;
      $('#targetInferenceFps').value = settings.target_inference_fps;
      $('#crowdThreshold').value = settings.crowd_threshold;
      $('#alertCooldown').value = settings.alert_cooldown_seconds;
      $('#themeSetting').value = settings.theme;
      $('#saveScreenshots').checked = settings.save_alert_screenshots;
      $('#heatmapOpacity').value = settings.heatmap_opacity;
      $('#heatmapOutput').textContent = `${Math.round(settings.heatmap_opacity * 100)}%`;
      this.applyTheme(settings.theme);
    }

    sourceUi() {
      const type = $('#sourceType').value;
      const input = $('#cameraSource');
      const hints = {
        webcam: ['0', 'Local webcam index, usually 0.'],
        usb: ['0', 'USB camera index, usually 0 or 1.'],
        rtsp: ['rtsp://user:password@camera/stream', 'Use the complete RTSP stream URL.'],
        ip: ['http://camera/video', 'Use an HTTP or HTTPS camera stream.'],
        video: ['', 'Upload a supported video, then its filename is selected automatically.'],
      };
      input.placeholder = hints[type][0];
      const webcam = type === 'webcam' || type === 'usb'; input.classList.toggle('d-none', webcam); $('#webcamDeviceSelect').classList.toggle('d-none', !webcam); if (webcam) this.enumerateCameras();
      if (type === 'video' && !input.value.includes('.')) input.value = '';
      $('#sourceHint').textContent = hints[type][1];
      $('#uploadStrip').classList.toggle('d-none', type !== 'video');
    }

    async enumerateCameras() { try { if (!navigator.mediaDevices?.enumerateDevices) return; if (this.state.cameraPermission !== 'granted') { const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); stream.getTracks().forEach(track => track.stop()); this.state.cameraPermission = 'granted'; } const devices = (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput'); const select = $('#webcamDeviceSelect'); select.innerHTML = devices.length ? devices.map((device, index) => `<option value="${index}">${escapeHtml(device.label || `Camera ${index + 1}`)}</option>`).join('') : '<option value="">No cameras detected</option>'; if (devices.length) $('#cameraSource').value = select.value; } catch (error) { this.state.cameraPermission = 'denied'; $$(`#sourceType option[value="webcam"], #sourceType option[value="usb"]`).forEach(option => option.disabled = true); $('#sourceType').value = 'video'; this.sourceUi(); this.notify('Camera permission was denied. Webcam options were disabled; upload a video instead.', 'warning'); } }

    async refreshCameras(selectPreferred = false) {
      const cameras = await this.api.request('/api/cameras');
      const signature = JSON.stringify(cameras.map(camera => [camera.id, camera.active, camera.paused, camera.error, camera.name]));
      const previousSignature = this.state.cameraSignature;
      this.state.cameras = cameras;
      this.state.cameraSignature = signature;
      const selectedExists = cameras.some(camera => camera.id === this.state.cameraId);
      if ((!this.state.cameraId || !selectedExists || selectPreferred) && cameras.length) {
        this.state.cameraId = (cameras.find(camera => camera.active) || cameras[0]).id;
      }
      if (signature !== previousSignature || selectPreferred) this.renderCameras();
      this.renderCameraSelectors();
      this.updateHomeMetrics();
    }

    renderCameras() {
      const container = $('#cameraList');
      if (!this.state.cameras.length) {
        container.className = 'camera-list empty-state';
        container.textContent = 'No camera is connected.';
        return;
      }
      container.className = 'camera-list';
      container.innerHTML = this.state.cameras.map(camera => `
        <button class="camera-card ${camera.id === this.state.cameraId ? 'active' : ''}" data-camera="${escapeHtml(camera.id)}" type="button">
          <span class="camera-state ${camera.active ? '' : 'stopped'}">${camera.active ? 'LIVE' : 'STOPPED'}</span>
          <b>${escapeHtml(camera.name)}</b><small>${escapeHtml(camera.source_type)} | ${escapeHtml(camera.source)}</small>
        </button>
      `).join('');
      $$('.camera-card').forEach(button => button.addEventListener('click', () => {
        this.state.cameraId = button.dataset.camera;
        this.state.feedKey = '';
        this.renderCameras();
        this.bindFeed();
        this.poll();
      }));
    }

    renderCameraSelectors() {
      ['reportCamera', 'analyticsCamera'].forEach(id => {
        const select = $(`#${id}`);
        const prior = select.value;
        select.innerHTML = '<option value="">All cameras</option>' + this.state.cameras.map(camera =>
          `<option value="${escapeHtml(camera.id)}">${escapeHtml(camera.name)}</option>`).join('');
        select.value = this.state.cameras.some(camera => camera.id === prior) ? prior : '';
      });
    }

    async startCamera() {
      const sourceType = $('#sourceType').value;
      const source = (sourceType === 'webcam' || sourceType === 'usb') ? $('#webcamDeviceSelect').value : $('#cameraSource').value.trim();
      if (['rtsp', 'ip', 'video'].includes(sourceType) && !source) {
        this.notify(sourceType === 'video' ? 'Upload a video before starting analysis.' : 'Enter a camera stream URL.', 'warning');
        return;
      }
      const stages = ['Initializing AI...', 'Loading Detection Engine...', 'Opening Camera...', 'Preparing Tracker...', 'Starting Video Stream...', 'Almost Ready...'];
      let stage = 0;
      const stageTimer = window.setInterval(() => {
        stage = Math.min(stage + 1, stages.length - 1);
        $('#operationTitle').textContent = stages[stage];
      }, 500);
      try {
        const stats = await this.withBusy(stages[0], 'Preparing the local detection and tracking pipeline.', () => this.api.request('/api/cameras/start', {
          method: 'POST',
          body: JSON.stringify({ source_type: sourceType, source: source || 0, name: $('#cameraName').value.trim() }),
        }));
        $('#operationTitle').textContent = stages[4];
        $('#operationDetail').textContent = 'Waiting for the first processed frame.';
        $('#operationOverlay').classList.remove('d-none');
        this.state.cameraId = stats.camera_id;
        this.state.feedKey = '';
        await this.refreshCameras(true);
        this.showPage('monitoring');
        await this.waitForFirstFrame();
        $('#operationOverlay').classList.add('d-none');
        this.notify('Monitoring started.', 'success');
        this.poll();
      } catch (error) {
        if (this.state.cameraId && !$('#videoFeed').naturalWidth) {
          try {
            await this.api.request(`/api/monitoring/${encodeURIComponent(this.state.cameraId)}/stop`, { method: 'POST', body: '{}' });
            await this.refreshCameras();
          } catch (_) {}
        }
        this.notify(error.message, 'danger');
      } finally {
        window.clearInterval(stageTimer);
        $('#operationOverlay').classList.add('d-none');
      }
    }

    waitForFirstFrame() {
      const image = $('#videoFeed');
      return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('Camera opened, but no video frame was received. Check whether it is busy or disconnected.')), 15000);
        image.onload = () => { window.clearTimeout(timeout); image.classList.add('visible'); $('#videoEmpty').style.display = 'none'; resolve(); };
        image.onerror = () => { window.clearTimeout(timeout); reject(new Error('The video stream was lost. Check the camera connection and try again.')); };
        this.bindFeed();
      });
    }

    async cameraAction(action) {
      if (!this.state.cameraId) {
        this.notify('Select an active camera first.', 'warning');
        return;
      }
      const labels = { pause: 'Pausing camera...', resume: 'Resuming camera...', stop: 'Stopping camera...' };
      try {
        await this.withBusy(labels[action], 'Updating the camera processing lifecycle.', () => this.api.request(
          `/api/monitoring/${encodeURIComponent(this.state.cameraId)}/${action}`,
          { method: 'POST', body: '{}' },
        ));
        if (action === 'stop') this.state.feedKey = '';
        await this.refreshCameras();
        this.bindFeed();
        this.poll();
        this.notify(`Camera ${action === 'stop' ? 'stopped' : `${action}d`}.`, action === 'stop' ? 'secondary' : 'success');
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    bindFeed() {
      const selected = this.state.cameras.find(camera => camera.id === this.state.cameraId);
      const image = $('#videoFeed');
      if (!selected?.active) {
        image.removeAttribute('src');
        image.classList.remove('visible');
        $('#videoEmpty').style.display = 'grid';
        return;
      }
      const feedKey = `${selected.id}:${this.state.mode}`;
      image.classList.remove('visible');
      $('#videoEmpty').style.display = 'grid';
      image.onerror = () => { this.notify('The video stream was lost. Check the camera connection and try again.', 'danger'); };
      if (feedKey !== this.state.feedKey) {
        image.src = `/video_feed/${encodeURIComponent(selected.id)}?mode=${this.state.mode}&_=${Date.now()}`;
        this.state.feedKey = feedKey;
      }
      if (image.complete && image.naturalWidth) {
        image.classList.add('visible');
        $('#videoEmpty').style.display = 'none';
      }
    }

    updateLiveControls(statistics) {
      const running = Boolean(statistics?.running);
      ['pauseCamera', 'resumeCamera', 'stopCamera', 'snapshotCamera'].forEach(id => { $(`#${id}`).disabled = !running; });
      $('#currentCameraLabel').textContent = statistics?.camera_name || 'No active camera';
      $('#cameraDetail').textContent = statistics?.error || (statistics?.paused
        ? 'Monitoring paused. The latest processed frame is retained.'
        : statistics?.source_type ? `${statistics.source_type.toUpperCase()} source | AI tracking enabled` : 'Connect a source to start AI analysis.');
      $('#sidebarStatus').textContent = running ? (statistics.paused ? 'Paused' : 'Monitoring') : 'Ready';
      $('#systemChip').innerHTML = `<i class="fa-solid fa-circle"></i><span>${running ? (statistics.paused ? 'Monitoring paused' : 'Monitoring live') : 'System ready'}</span>`;
    }

    updateStatistics(statistics) {
      if (!statistics || statistics.cameras) return;
      $('#occupancyValue').textContent = formatNumber(statistics.occupancy);
      $('#trackingValue').textContent = formatNumber(statistics.tracking_count);
      $('#fpsValue').textContent = Number(statistics.fps || 0).toFixed(1);
      $('#runtimeValue').textContent = `${formatRuntime(statistics.runtime_seconds || 0)} runtime`;
      $('#densityValue').textContent = `${statistics.density || 'Low'} density`;
      $('#lineValue').textContent = `${statistics.people_entered || 0} / ${statistics.people_exited || 0}`;
      $('#homeOccupancy').textContent = formatNumber(statistics.occupancy);
      $('#homeAverage').textContent = formatNumber(statistics.analytics?.average);
      $('#homePeak').textContent = formatNumber(statistics.analytics?.peak);
      this.updateLiveControls(statistics);
      if (!statistics.running && statistics.error) {
        this.state.feedKey = '';
        this.bindFeed();
      }
      this.renderZones(statistics.zones || []);
      this.renderAlerts(statistics.alerts || []);
      this.updateLiveChart(statistics.analytics?.history || []);
      if (statistics.error && !this.state.shownErrors.has(statistics.error)) {
        this.state.shownErrors.add(statistics.error);
        this.notify(statistics.error, 'danger');
      }
    }

    updateAggregate(aggregate) {
      if (!aggregate?.aggregate) return;
      const values = aggregate.aggregate;
      $('#homeCameras').textContent = formatNumber(aggregate.active_cameras);
      $('#homeOccupancy').textContent = formatNumber(values.occupancy);
      $('#homeAverage').textContent = formatNumber(values.average_occupancy);
      $('#homePeak').textContent = formatNumber(values.peak_occupancy || values.max_occupancy);
      $('#homeAlerts').textContent = formatNumber(values.alerts);
    }

    updateHomeMetrics() {
      $('#homeCameras').textContent = formatNumber(this.state.cameras.filter(camera => camera.active).length);
    }

    renderZones(zones) {
      const container = $('#zoneList');
      if (!zones.length) {
        container.className = 'zone-list empty-state';
        container.textContent = 'No restricted zones configured.';
        return;
      }
      container.className = 'zone-list';
      container.innerHTML = zones.map(zone => `<div class="zone-row"><span><b>${escapeHtml(zone.name)}</b><small>Threshold ${zone.alert_threshold ?? 'not set'}</small></span><b>${formatNumber(zone.occupancy)} people</b></div>`).join('');
    }

    renderAlerts(alerts) {
      const container = $('#alertList');
      if (!alerts.length) {
        container.className = 'activity-list empty-state';
        container.textContent = 'No alerts triggered.';
        return;
      }
      container.className = 'activity-list';
      container.innerHTML = alerts.map(alert => `<div class="activity-item"><span class="activity-icon"><i class="fa-solid fa-triangle-exclamation"></i></span><span><b>${escapeHtml(alert.message)}</b><small>${escapeHtml(alert.type)} | ${alert.payload?.screenshot ? 'evidence saved' : 'recorded'}</small></span></div>`).join('');
      alerts.forEach(alert => {
        if (!this.state.knownAlerts.has(alert.id)) {
          this.state.knownAlerts.add(alert.id);
          $('#alertBanner').classList.remove('d-none');
          $('#alertMessage').textContent = alert.message;
          this.playAlert();
        }
      });
    }

    updateLiveChart(history) {
      const canvas = $('#liveOccupancyChart');
      if (!window.Chart || !canvas) return;
      const labels = history.map(sample => new Date(sample.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      const values = history.map(sample => sample.occupancy);
      if (!this.state.liveChart) {
        this.state.liveChart = new Chart(canvas, {
          type: 'line',
          data: { labels, datasets: [{ label: 'Occupancy', data: values, borderColor: '#766ff5', backgroundColor: 'rgba(118,111,245,0.12)', fill: true, pointRadius: 0, tension: 0.34 }] },
          options: this.compactChartOptions(),
        });
      } else {
        this.state.liveChart.data.labels = labels;
        this.state.liveChart.data.datasets[0].data = values;
        this.state.liveChart.update('none');
      }
    }

    compactChartOptions() {
      return {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#8f9bb4', maxTicksLimit: 6, font: { size: 10 } } },
          y: { beginAtZero: true, ticks: { precision: 0, color: '#8f9bb4', font: { size: 10 } }, grid: { color: 'rgba(130,145,170,0.16)' } },
        },
      };
    }

    playAlert() {
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const context = new AudioContext();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = 740;
        gain.gain.setValueAtTime(0.045, context.currentTime);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.15);
      } catch (_) {
        // Browser media policies can reject sound before the first user gesture.
      }
    }

    async poll() {
      if (!this.state.accepted || this.state.pollInFlight || document.hidden) return;
      this.state.pollInFlight = true;
      try {
        if (this.state.cameraId) {
          this.updateStatistics(await this.api.request(`/api/monitoring/statistics?camera_id=${encodeURIComponent(this.state.cameraId)}`));
        } else {
          this.updateAggregate(await this.api.request('/api/monitoring/statistics'));
        }
        this.state.pollCount += 1;
        if (this.state.pollCount % 6 === 0) {
          await this.refreshCameras();
        }
      } catch (error) {
        if (!this.state.shownErrors.has(error.message)) {
          this.state.shownErrors.add(error.message);
          this.notify(error.message, 'danger');
        }
      } finally {
        this.state.pollInFlight = false;
      }
    }

    startPolling() {
      this.stopPolling();
      this.state.pollTimer = window.setInterval(() => this.poll(), 5000);
    }

    stopPolling() {
      if (this.state.pollTimer) window.clearInterval(this.state.pollTimer);
      this.state.pollTimer = null;
    }

    async uploadVideo(file) {
      if (!file) return;
      const form = new FormData();
      form.append('video', file);
      try {
        $('#uploadStatus').textContent = `Uploading ${file.name}...`;
        const response = await this.withBusy('Uploading video...', 'Validating and saving the selected video file.', () => this.api.request('/api/monitoring/upload', { method: 'POST', body: form }));
        $('#cameraSource').value = response.filename;
        $('#uploadStatus').textContent = `${file.name} ready (${Math.round(response.size_bytes / 1024 / 1024 * 10) / 10} MB)`;
        this.notify('Video uploaded and ready to analyze.', 'success');
      } catch (error) {
        $('#uploadStatus').textContent = 'Upload failed';
        this.notify(error.message, 'danger');
      }
    }

    async takeSnapshot() {
      if (!this.state.cameraId) return;
      try {
        const shot = await this.withBusy('Saving screenshot...', 'Writing a timestamped evidence image.', () => this.api.request(
          `/api/monitoring/${encodeURIComponent(this.state.cameraId)}/snapshot`, { method: 'POST', body: '{}' },
        ));
        this.notify('Screenshot saved.', 'success');
        window.open(shot.url, '_blank', 'noopener');
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    async saveGeometry(type) {
      if (!this.state.cameraId) {
        this.notify('Start and select a camera before configuring safety geometry.', 'warning');
        return;
      }
      try {
        const input = type === 'zones' ? $('#zonesInput') : $('#lineInput');
        const raw = input.value.trim();
        const payload = type === 'zones' ? { zones: raw ? JSON.parse(raw) : [] } : { line: raw ? JSON.parse(raw) : null };
        await this.withBusy('Saving safety geometry...', 'Validating the selected camera coordinates.', () => this.api.request(
          `/api/monitoring/${encodeURIComponent(this.state.cameraId)}/${type === 'zones' ? 'zones' : 'counting-line'}`,
          { method: 'POST', body: JSON.stringify(payload) },
        ));
        this.notify(`${type === 'zones' ? 'Zones' : 'Counting line'} saved.`, 'success');
        this.poll();
      } catch (error) {
        this.notify(`Safety geometry was not saved: ${error.message}`, 'danger');
      }
    }

    async loadLogs() {
      try {
        const category = $('#logFilter').value;
        const events = await this.api.request(`/api/logs?limit=200${category ? `&category=${encodeURIComponent(category)}` : ''}`);
        this.renderLogs(events);
        this.renderHomeActivity(events);
        $('#homeAlerts').textContent = formatNumber(events.filter(event => event.category === 'alert').length);
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    renderLogs(events) {
      const table = $('#logTable');
      if (!events.length) {
        table.innerHTML = '<tr><td colspan="6" class="empty-state">No logged events.</td></tr>';
        return;
      }
      table.innerHTML = events.map(event => `
        <tr><td>${escapeHtml(formatDate(event.created_at))}</td><td>${escapeHtml(event.category)}</td>
        <td><span class="pill ${escapeHtml(event.level)}">${escapeHtml(event.level)}</span></td><td>${escapeHtml(event.camera_id || '-')}</td>
        <td>${escapeHtml(event.message)}</td><td>${event.payload?.screenshot ? `<a class="download-link" target="_blank" href="/api/screenshots/${encodeURIComponent(event.payload.screenshot)}">View image</a>` : event.payload?.filename ? escapeHtml(event.payload.filename) : '-'}</td></tr>
      `).join('');
    }

    renderHomeActivity(events) {
      const container = $('#homeActivity');
      const recent = events.slice(0, 4);
      if (!recent.length) {
        container.className = 'activity-list empty-state';
        container.textContent = 'No events have been recorded yet.';
        return;
      }
      container.className = 'activity-list';
      container.innerHTML = recent.map(event => `
        <div class="activity-item"><span class="activity-icon"><i class="fa-solid ${event.level === 'ERROR' ? 'fa-circle-xmark' : event.category === 'alert' ? 'fa-bell' : 'fa-circle-check'}"></i></span>
        <span><b>${escapeHtml(event.message)}</b><small>${escapeHtml(event.category)} | ${escapeHtml(formatDate(event.created_at))}</small></span></div>
      `).join('');
    }

    async loadReports() {
      try {
        const reports = await this.api.request('/api/reports');
        const table = $('#reportTable');
        if (!reports.length) {
          table.innerHTML = '<tr><td colspan="4" class="empty-state">No reports generated.</td></tr>';
          return;
        }
        table.innerHTML = reports.map(report => `
          <tr><td>${escapeHtml(formatDate(report.created_at))}</td><td><span class="pill">${escapeHtml(report.format.toUpperCase())}</span></td>

          <td>
              Peak: <b>${formatNumber(report.summary.current_occupancy)}</b> people
              &nbsp;|&nbsp;
              <b>${formatNumber(report.summary.alerts)}</b> alert${report.summary.alerts === 1 ? '' : 's'}
              &nbsp;|&nbsp;
              <b>${formatNumber(report.summary.incidents)}</b> incident${report.summary.incidents === 1 ? '' : 's'}
              &nbsp;|&nbsp;
              <b>${formatNumber(report.summary.screenshots)}</b> screenshot${report.summary.screenshots === 1 ? '' : 's'}
          </td>

          <td><a class="download-link" href="/api/reports/download/${encodeURIComponent(report.filename)}"><i class="fa-solid fa-download"></i> Download</a></td></tr>
        `).join('');
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    async generateReport() {
      try {
        const report = await this.withBusy(
          'Generating report...',
          'Collecting operational metrics, incidents, and evidence.',
          () => this.api.request('/api/reports/generate', {
            method: 'POST',
            body: JSON.stringify({
              format: $('#reportFormat').value,
              camera_id: $('#reportCamera').value || null,
            }),
          })
        );

        await this.loadReports();

        this.notify(
          'Report generated successfully. Your evidence package is ready.',
          'success'
        );

        window.open(report.download_url, '_blank', 'noopener');

      } catch (error) {

        const message = (error.message || "").toLowerCase();

        if (
          message.includes("nothing to export") ||
          message.includes("no monitoring") ||
          message.includes("no evidence")
        ) {

          this.notify(
            "Nothing to export. Start monitoring and generate some activity before creating a report.",
            "warning"
          );

          return;
        }

        this.notify(error.message, 'danger');
      }
    }

    analyticsQuery() {
      const query = new URLSearchParams({ range: this.state.selectedRange });
      const camera = $('#analyticsCamera').value;
      if (camera) query.set('camera_id', camera);
      if (this.state.selectedRange === 'custom') {
        const start = $('#analyticsStart').value;
        const end = $('#analyticsEnd').value;
        if (!start || !end) throw new Error('Select both custom range dates.');
        query.set('start', new Date(start).toISOString());
        query.set('end', new Date(end).toISOString());
      }
      return query;
    }

    async loadAnalytics() {
      try {
        const query = this.analyticsQuery();
        const data = await this.api.request(`/api/analytics/history?${query.toString()}`);
        this.state.latestHistory = data.samples || [];
        $('#analyticsRangeLabel').textContent = formatRange(this.state.selectedRange);
        this.updateHistoryChart(this.state.latestHistory);
        this.renderAnalyticsSummary(this.state.latestHistory);
      } catch (error) {
        this.notify(error.message, 'warning');
      }
    }

    updateHistoryChart(samples) {
      const canvas = $('#historyChart');
      const empty = $('#historyEmpty');
      if (!window.Chart || !canvas) return;
      const labels = samples.map(sample => new Date(sample.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }));
      const datasets = [
        { label: 'Occupancy', data: samples.map(sample => sample.occupancy), borderColor: '#766ff5', backgroundColor: 'rgba(118,111,245,0.12)', fill: true, pointRadius: 0, tension: 0.32 },
        { label: 'Tracking count', data: samples.map(sample => sample.tracking_count), borderColor: '#159b9e', backgroundColor: 'transparent', fill: false, pointRadius: 0, tension: 0.32 },
      ];
      empty.classList.toggle('d-none', samples.length > 0);
      if (!this.state.historyChart) {
        this.state.historyChart = new Chart(canvas, {
          type: 'line', data: { labels, datasets }, options: {
            ...this.compactChartOptions(),
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: { mode: 'index', intersect: false },
              zoom: {
                pan: { enabled: true, mode: 'x', modifierKey: 'shift' },
                zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
              },
            },
          },
        });
      } else {
        this.state.historyChart.data.labels = labels;
        this.state.historyChart.data.datasets = datasets;
        this.state.historyChart.resetZoom?.();
        this.state.historyChart.update('none');
      }
    }

    renderAnalyticsSummary(samples) {
      const values = samples.map(sample => Number(sample.occupancy));
      const tracking = samples.map(sample => Number(sample.tracking_count));
      const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
      $('#analyticsSummary').innerHTML = [
        ['Samples', formatNumber(samples.length)],
        ['Average occupancy', average.toFixed(1)],
        ['Maximum occupancy', formatNumber(Math.max(0, ...values))],
        ['Peak tracking count', formatNumber(Math.max(0, ...tracking))],
      ].map(([label, value]) => `<div class="summary-item"><span>${label}</span><b>${value}</b></div>`).join('');
    }

    exportAnalytics(format) {
      try {
        const query = this.analyticsQuery();
        query.set('format', format);
        window.location.assign(`/api/analytics/export?${query.toString()}`);
      } catch (error) {
        this.notify(error.message, 'warning');
      }
    }

    async saveSettings(event) {
      event.preventDefault();
      const settings = {
        confidence_threshold: Number($('#confidenceThreshold').value),
        target_inference_fps: Number($('#targetInferenceFps').value),
        crowd_threshold: Number($('#crowdThreshold').value),
        alert_cooldown_seconds: Number($('#alertCooldown').value),
        theme: $('#themeSetting').value,
        save_alert_screenshots: $('#saveScreenshots').checked,
        heatmap_opacity: Number($('#heatmapOpacity').value),
      };
      try {
        this.loadSettings(await this.withBusy('Saving settings...', 'Applying safe runtime configuration updates.', () => this.api.request('/api/settings', { method: 'PUT', body: JSON.stringify(settings) })));
        this.notify('Settings saved and applied.', 'success');
      } catch (error) {
        this.notify(error.message, 'danger');
      }
    }

    renderHealth(health) {
      if (!health) return;
      const ready = Boolean(health.ready);
      $('#homeHealth').textContent = ready ? 'Ready' : 'Attention';
      $('#healthSummary').innerHTML = (health.components || []).slice(0, 5).map(component => `
        <div class="health-item ${component.ready ? '' : 'critical'}"><i class="fa-solid ${component.ready ? 'fa-circle-check' : 'fa-circle-exclamation'}"></i>
        <span>${escapeHtml(component.title)}</span><small>${component.ready ? 'Ready' : 'Needs attention'}</small></div>
      `).join('');
    }

    async recheckHealth() {
      const health = await this.withBusy('Checking platform health...', 'Verifying backend, storage, AI model, and configuration.', () => this.api.health());
      this.state.health = health;
      this.renderHealth(health);
      this.notify(health.ready ? 'All platform checks are healthy.' : 'One or more platform checks need attention.', health.ready ? 'success' : 'warning');
    }

    bindEvents() {
      $$('.main-nav a').forEach(link => link.addEventListener('click', event => { event.preventDefault(); this.showPage(link.dataset.page); }));
      $$('[data-go]').forEach(button => button.addEventListener('click', () => this.showPage(button.dataset.go)));
      $$('.quick-action').forEach(button => button.addEventListener('click', () => { this.showPage('monitoring'); $('#sourceType').value = button.dataset.quickSource; this.sourceUi(); }));
      $('#retryStartup').addEventListener('click', async () => { $('#diagnosticOverlay').classList.add('d-none'); $('#startupOverlay').classList.remove('d-none', 'complete'); const health = await this.runStartupSequence(); if (health.ready) { this.state.health = health; this.hideStartup(); this.showConsent(); } else this.showDiagnostics(health); });
      $('#acceptConsent').addEventListener('click', () => this.acceptConsent());
      $('#declineConsent').addEventListener('click', () => this.declineConsent());
      $('#returnConsent').addEventListener('click', () => this.showConsent());
      $('#closeApplication').addEventListener('click', () => { window.close(); $('#closeHint').classList.remove('d-none'); });
      $('#collapseSidebar').addEventListener('click', () => this.toggleSidebar());
      $('#mobileMenu').addEventListener('click', () => $('#sidebar').classList.toggle('mobile-open'));
      $('#themeToggle').addEventListener('click', () => this.applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true));
      $('#recheckHealth').addEventListener('click', () => this.recheckHealth().catch(error => this.notify(error.message, 'danger')));
      $('#sourceType').addEventListener('change', () => this.sourceUi());
      $('#webcamDeviceSelect').addEventListener('change', event => { $('#cameraSource').value = event.target.value; });
      $('#startCamera').addEventListener('click', () => this.startCamera());
      $('#refreshCameras').addEventListener('click', () => this.refreshCameras(true).catch(error => this.notify(error.message, 'danger')));
      $('#uploadVideo').addEventListener('click', () => $('#videoUpload').click());
      $('#videoUpload').addEventListener('change', event => this.uploadVideo(event.target.files[0]));
      $('#pauseCamera').addEventListener('click', () => this.cameraAction('pause'));
      $('#resumeCamera').addEventListener('click', () => this.cameraAction('resume'));
      $('#stopCamera').addEventListener('click', () => this.cameraAction('stop'));
      $('#snapshotCamera').addEventListener('click', () => this.takeSnapshot());
      $('#fullscreenCamera').addEventListener('click', () => $('#videoStage').requestFullscreen?.());
      $$('.video-mode').forEach(button => button.addEventListener('click', () => { this.state.mode = button.dataset.mode; this.state.feedKey = ''; $$('.video-mode').forEach(item => item.classList.toggle('active', item === button)); this.bindFeed(); }));
      $('#dismissAlert').addEventListener('click', () => $('#alertBanner').classList.add('d-none'));
      $('#saveZones').addEventListener('click', () => this.saveGeometry('zones'));
      $('#saveLine').addEventListener('click', () => this.saveGeometry('line'));
      $('#refreshLogs').addEventListener('click', () => this.loadLogs());
      $('#logFilter').addEventListener('change', () => this.loadLogs());
      $('#generateReport').addEventListener('click', () => this.generateReport());
      $('#refreshReports').addEventListener('click', () => this.loadReports());
      $('#settingsForm').addEventListener('submit', event => this.saveSettings(event));
      $('#confidenceThreshold').addEventListener('input', event => { $('#confidenceOutput').textContent = `${Math.round(Number(event.target.value) * 100)}%`; });
      $('#heatmapOpacity').addEventListener('input', event => { $('#heatmapOutput').textContent = `${Math.round(Number(event.target.value) * 100)}%`; });
      $$('.range-button').forEach(button => button.addEventListener('click', () => { this.state.selectedRange = button.dataset.range; $$('.range-button').forEach(item => item.classList.toggle('active', item === button)); $('#customRangeInputs').classList.toggle('d-none', this.state.selectedRange !== 'custom'); if (this.state.selectedRange !== 'custom') this.loadAnalytics(); }));
      $('#applyCustomRange').addEventListener('click', () => this.loadAnalytics());
      $('#analyticsCamera').addEventListener('change', () => this.loadAnalytics());
      $('#resetAnalyticsZoom').addEventListener('click', () => this.state.historyChart?.resetZoom?.());
      $('#exportAnalyticsCsv').addEventListener('click', () => this.exportAnalytics('csv'));
      $('#exportAnalyticsJson').addEventListener('click', () => this.exportAnalytics('json'));
      window.addEventListener('popstate', () => this.showPage(location.pathname.split('/')[1] || 'home', false));
      document.addEventListener('visibilitychange', () => { if (document.hidden) this.stopPolling(); else if (this.state.accepted) { this.poll(); this.startPolling(); } });
      const cameraHelpBtn = document.getElementById("cameraSourceHelp");

      if (cameraHelpBtn) {

          cameraHelpBtn.addEventListener("click", () => {

              new bootstrap.Modal(
                  document.getElementById("cameraSourceModal")
              ).show();

          });

      }    


    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    window.smartCrowdApp = new DashboardApp();
    window.smartCrowdApp.boot();
  });
})();



document.addEventListener("DOMContentLoaded", () => {

    const canvas = document.getElementById("geometryCanvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");

    const videoFeed = document.getElementById("videoFeed");

    const modeText = document.getElementById("geometryMode");
    const pointText = document.getElementById("geometryPoints");

    const drawZoneBtn = document.getElementById("drawZoneBtn");
    const drawLineBtn = document.getElementById("drawLineBtn");
    const undoBtn = document.getElementById("undoGeometryBtn");
    const clearBtn = document.getElementById("clearGeometryBtn");
    const saveGeometryBtn = document.getElementById("saveGeometryBtn");

    let mode = "zone";

    let points = [];

    let canvasReady = false;

    function syncCanvas() {

        if (!videoFeed.complete) return false;

        if (videoFeed.naturalWidth === 0) return false;

        canvas.width = videoFeed.naturalWidth;
        canvas.height = videoFeed.naturalHeight;

        canvasReady = true;

        return true;

    }

    function updateStatus() {

        modeText.textContent =
            "Mode : " + (mode === "zone" ? "Zone" : "Line");

        pointText.textContent =
            "Points : " + points.length;

    }

    function clearCanvas() {

        ctx.clearRect(
            0,
            0,
            canvas.width,
            canvas.height
        );

    }

    function drawBackground() {

        if (!canvasReady) {

            if (!syncCanvas()) return;

        }

        clearCanvas();

        ctx.drawImage(

            videoFeed,

            0,
            0,

            canvas.width,
            canvas.height

        );

    }

    function drawPoints() {

        for (const p of points) {

            ctx.beginPath();

            ctx.arc(

                p.x,
                p.y,
                6,
                0,
                Math.PI * 2

            );

            ctx.fillStyle = "#6c63ff";

            ctx.fill();

        }

    }


function redraw() {

    drawBackground();

    if (!canvasReady) return;

    if (points.length > 0) {

        ctx.beginPath();

        ctx.moveTo(points[0].x, points[0].y);

        for (let i = 1; i < points.length; i++) {

            ctx.lineTo(points[i].x, points[i].y);

        }

        if (mode === "zone" && points.length >= 3) {

            ctx.closePath();

            ctx.fillStyle = "rgba(0,184,148,0.18)";
            ctx.fill();

            ctx.strokeStyle = "#00b894";

        } else {

            ctx.strokeStyle = "#1e88ff";

        }

        ctx.lineWidth = 3;
        ctx.stroke();

    }

    drawPoints();

    updateStatus();

}

drawZoneBtn.onclick = () => {

    mode = "zone";
    points = [];
    redraw();

};

drawLineBtn.onclick = () => {

    mode = "line";
    points = [];
    redraw();

};

undoBtn.onclick = () => {

    if (points.length) {

        points.pop();
        redraw();

    }

};

clearBtn.onclick = () => {

    points = [];
    redraw();

};

canvas.onclick = function (e) {

    if (!canvasReady) return;

    const rect = canvas.getBoundingClientRect();

    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    if (mode === "line") {

        if (points.length === 2)
            points = [];

        points.push({ x, y });

    } else {

        points.push({ x, y });

    }

    redraw();

};

canvas.ondblclick = function () {

    if (mode !== "zone") return;

    if (points.length < 3) return;

    redraw();

};

const geometryModal = document.getElementById("geometryModal");

geometryModal.addEventListener("shown.bs.modal", () => {

    canvasReady = false;

    syncCanvas();

    redraw();

});




saveGeometryBtn.onclick = function () {

    if (!canvasReady) {

        window.smartCrowdApp?.notify("Video frame not ready.", "warning");
        return;

    }

    if (mode === "zone") {

        if (points.length < 3) {

            window.smartCrowdApp?.notify("Draw at least 3 points.", "warning");
            return;

        }

          const threshold = Number(
              document.getElementById("zoneThresholdInput").value
          ) || 10;

          const zone = [{
              name: "Restricted Zone",
              points: points.map(p => [p.x, p.y]),
              alert_threshold: threshold
          }];

        document.getElementById("zonesInput").value =
            JSON.stringify(zone, null, 2);

        document.getElementById("saveZones").click();

    } else {

        if (points.length !== 2) {

            window.smartCrowdApp?.notify("Draw exactly 2 points.", "warning");
            return;

        }

        const line = {

            start: [points[0].x, points[0].y],
            end: [points[1].x, points[1].y]

        };

        document.getElementById("lineInput").value =
            JSON.stringify(line, null, 2);

        document.getElementById("saveLine").click();

    }

    bootstrap.Modal
        .getInstance(document.getElementById("geometryModal"))
        .hide();

};

updateStatus();

});

document.addEventListener("DOMContentLoaded", () => {

    const openBtn = document.getElementById("openGeometryEditor");
    const modalEl = document.getElementById("geometryModal");

    if (!openBtn || !modalEl) return;

    const geometryModal = new bootstrap.Modal(modalEl);

    openBtn.addEventListener("click", () => {
        geometryModal.show();
    });

});

function checkDesktopDevice() {

    const overlay = document.getElementById("desktopOnlyOverlay");
    const app = document.getElementById("appRoot");

    if (!overlay || !app) return;

    if (window.innerWidth < 992) {
        overlay.style.display = "flex";
        app.style.display = "none";
    } else {
        overlay.style.display = "none";
        app.style.display = "";
    }
}

window.addEventListener("load", checkDesktopDevice);
let desktopResizeTimer;
window.addEventListener("resize", () => {
    window.clearTimeout(desktopResizeTimer);
    desktopResizeTimer = window.setTimeout(checkDesktopDevice, 150);
});
