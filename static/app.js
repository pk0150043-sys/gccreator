/* ==========================================================================
   SERVER GOD CLAN ✦ 3D WEB ENGINE CLIENT CONTROLLER
   ========================================================================== */

let currentUser = null;
let currentToken = null;
let ws = null;
let pingInterval = null;
let selectedSessionLabel = null;
let savedSessionsMap = {};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
  initParticleCanvas();
  init3DCardTilt();
  checkExistingAuth();
});

function initParticleCanvas() {
  const canvas = document.getElementById('matrixCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let width = canvas.width = window.innerWidth;
  let height = canvas.height = window.innerHeight;

  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });

  const particles = [];
  const numParticles = Math.min(65, Math.floor(width / 22));

  for (let i = 0; i < numParticles; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.8,
      vy: (Math.random() - 0.5) * 0.8,
      radius: Math.random() * 2 + 1,
      color: Math.random() > 0.4 ? 'rgba(255, 215, 0, ' : 'rgba(0, 240, 255, '
    });
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;

      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;
      if (p.y > height) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color + '0.7)';
      ctx.fill();

      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j];
        const dx = p.x - p2.x;
        const dy = p.y - p2.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 130) {
          const alpha = (1 - dist / 130) * 0.25;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.strokeStyle = p.color + alpha + ')';
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}

function init3DCardTilt() {
  const cards = document.querySelectorAll('.card-3d');
  cards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;
      const rotateX = (-y / rect.height) * 8;
      const rotateY = (x / rect.width) * 8;
      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg)';
    });
  });
}

// --- AUTHENTICATION ---
async function checkExistingAuth() {
  const savedToken = localStorage.getItem('sgc_token');
  const savedUser = localStorage.getItem('sgc_username');
  const savedRole = localStorage.getItem('sgc_role');

  if (savedToken && savedUser) {
    currentToken = savedToken;
    currentUser = { username: savedUser, role: savedRole };
    
    // Verify token validity
    try {
      const res = await fetch('/api/me', {
        headers: { 'Authorization': `Bearer ${currentToken}` }
      });
      const data = await res.json();
      if (data.success) {
        currentUser = data.user;
        showDashboard();
        return;
      }
    } catch (e) {
      console.warn('Auth check error:', e);
    }
  }
  showLogin();
}

function showLogin() {
  if (ws) ws.close();
  document.getElementById('loginScreen').classList.add('active');
  document.getElementById('dashboardScreen').classList.remove('active');
}

function showDashboard() {
  document.getElementById('loginScreen').classList.remove('active');
  document.getElementById('dashboardScreen').classList.add('active');

  // Update nav info
  document.getElementById('navUsername').textContent = currentUser.username;
  const roleBadge = document.getElementById('navUserRole');
  roleBadge.textContent = currentUser.role.toUpperCase();
  roleBadge.className = 'badge-role ' + (currentUser.role === 'owner' ? 'owner' : '');

  document.getElementById('userRoleIcon').textContent = currentUser.role === 'owner' ? '👑' : '👤';

  // Toggle Owner Features
  const isOwner = currentUser.role === 'owner';
  document.getElementById('ownerTabNav').style.display = isOwner ? 'flex' : 'none';
  document.getElementById('ownerLiveMonitorCard').style.display = isOwner ? 'block' : 'none';

  // Load Sessions & Status
  loadSessions();
  initWebSocket();
  fetchInitialTaskStatus();

  if (isOwner) {
    fetchUsersList();
    fetchLiveMonitor();
  }
}

let currentLoginMode = 'user';

function setLoginMode(mode) {
  currentLoginMode = mode;
  const userTab = document.getElementById('tabUserLogin');
  const ownerTab = document.getElementById('tabOwnerLogin');
  const uGroup = document.getElementById('loginUsernameGroup');
  const pLabel = document.getElementById('loginPasswordLabel');
  const pInput = document.getElementById('loginPassword');
  const btn = document.getElementById('loginBtn');

  if (mode === 'owner') {
    ownerTab.classList.add('active', 'owner-active');
    userTab.classList.remove('active');
    uGroup.style.display = 'none';
    pLabel.innerHTML = '<span class="icon">👑</span> OWNER ACCESS PASSWORD';
    pInput.placeholder = 'Enter Owner Secret Password';
    btn.className = 'btn-3d btn-primary';
    btn.querySelector('.btn-content').innerHTML = '<span class="btn-icon">👑</span> OWNER AUTHENTICATION';
  } else {
    userTab.classList.add('active');
    ownerTab.classList.remove('active', 'owner-active');
    uGroup.style.display = 'block';
    pLabel.innerHTML = '<span class="icon">🔑</span> PASSWORD';
    pInput.placeholder = 'Enter assigned password';
    btn.className = 'btn-3d btn-primary';
    btn.querySelector('.btn-content').innerHTML = '<span class="btn-icon">⚡</span> LOGIN TO SYSTEM';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  let uInput = '';
  if (currentLoginMode === 'owner') {
    uInput = 'OWNER';
  } else {
    uInput = document.getElementById('loginUsername').value.trim();
    if (!uInput) {
      showToast('Please enter your username', 'warn');
      return;
    }
  }

  const pInput = document.getElementById('loginPassword').value.trim();
  const btn = document.getElementById('loginBtn');

  btn.disabled = true;
  btn.querySelector('.btn-content').innerHTML = '⚡ AUTHENTICATING...';

  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uInput, password: pInput })
    });
    const data = await res.json();

    if (data.success) {
      currentToken = data.token;
      currentUser = { username: data.username, role: data.role };

      localStorage.setItem('sgc_token', currentToken);
      localStorage.setItem('sgc_username', currentUser.username);
      localStorage.setItem('sgc_role', currentUser.role);

      showToast(`Welcome, ${currentUser.username}! Logged in as ${currentUser.role.toUpperCase()}`, 'success');
      showDashboard();
    } else {
      showToast(data.message || 'Login failed: Invalid credentials', 'error');
    }
  } catch (err) {
    showToast('Network error during login', 'error');
  } finally {
    btn.disabled = false;
    btn.querySelector('.btn-content').innerHTML = currentLoginMode === 'owner' 
      ? '<span class="btn-icon">👑</span> OWNER AUTHENTICATION' 
      : '<span class="btn-icon">⚡</span> LOGIN TO SYSTEM';
  }
}

function handleLogout() {
  localStorage.removeItem('sgc_token');
  localStorage.removeItem('sgc_username');
  localStorage.removeItem('sgc_role');
  currentToken = null;
  currentUser = null;
  if (ws) ws.close();
  showToast('Logged out successfully', 'info');
  showLogin();
}

function togglePasswordVisibility(fieldId, btn) {
  const input = document.getElementById(fieldId);
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🔒';
  } else {
    input.type = 'password';
    btn.textContent = '👁️';
  }
}

function toggleTablePassword(spanId, btn) {
  const span = document.getElementById(spanId);
  if (!span) return;
  const rawPwd = span.getAttribute('data-pwd');
  if (span.textContent === '••••••••') {
    span.textContent = rawPwd;
    btn.textContent = '🔒';
  } else {
    span.textContent = '••••••••';
    btn.textContent = '👁️';
  }
}

// --- WEBSOCKET LIVE STREAMING ---
function initWebSocket() {
  if (ws) {
    ws.close();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/logs?token=${encodeURIComponent(currentToken)}`;

  ws = new WebSocket(wsUrl);

  const badge = document.getElementById('wsStatusBadge');

  ws.onopen = () => {
    badge.className = 'status-pill status-connected';
    badge.querySelector('.status-text').textContent = 'LIVE ONLINE';
    
    // Heartbeat ping
    if (pingInterval) clearInterval(pingInterval);
    pingInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 15000);
  };

  ws.onclose = () => {
    badge.className = 'status-pill status-disconnected';
    badge.querySelector('.status-text').textContent = 'OFFLINE';
    if (pingInterval) clearInterval(pingInterval);
    // Reconnect after 3 seconds if still on dashboard
    setTimeout(() => {
      if (currentToken) initWebSocket();
    }, 3000);
  };

  ws.onerror = (err) => {
    console.warn('WebSocket error:', err);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleWebSocketMessage(data);
    } catch (e) {
      console.warn('WS message parse error:', e);
    }
  };
}

function handleWebSocketMessage(data) {
  if (data.type === 'init_state') {
    updateTaskStatus(data.status);
    if (data.stats) updateStatsDisplay(data.stats);
    if (data.logs && data.logs.length > 0) {
      const terminal = document.getElementById('terminalBody');
      terminal.innerHTML = '';
      data.logs.forEach(l => appendLogLine(l.text, l.level));
    }
    if (data.created_gcs) renderCreatedThreads(data.created_gcs);
  } else if (data.type === 'log') {
    appendLogLine(data.text, data.level);
  } else if (data.type === 'stats') {
    updateStatsDisplay(data.stats);
  } else if (data.type === 'status') {
    updateTaskStatus(data.status);
  } else if (data.type === 'owner_monitor_update') {
    if (currentUser && currentUser.role === 'owner') {
      fetchLiveMonitor();
    }
  }
}

function appendLogLine(text, level = 'info') {
  const terminal = document.getElementById('terminalBody');
  const div = document.createElement('div');
  div.className = `term-line term-${level}`;
  div.textContent = text;
  terminal.appendChild(div);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearTerminal() {
  document.getElementById('terminalBody').innerHTML = '<div class="term-line term-system">🧹 [TERMINAL CLEARED]</div>';
}

function updateTaskStatus(status) {
  const pill = document.getElementById('taskStatusPill');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');

  pill.className = `badge-status badge-${status}`;
  pill.textContent = status.toUpperCase();

  if (status === 'running') {
    startBtn.style.display = 'none';
    stopBtn.style.display = 'inline-flex';
  } else {
    startBtn.style.display = 'inline-flex';
    stopBtn.style.display = 'none';
  }
}

function updateStatsDisplay(stats) {
  const total = stats.total || 0;
  const created = stats.created || 0;
  const failed = stats.failed || 0;
  const current = stats.current || 0;

  document.getElementById('statTotal').textContent = total;
  document.getElementById('statCreated').textContent = created;
  document.getElementById('statFailed').textContent = failed;
  document.getElementById('statCurrent').textContent = `#${current}`;

  // Progress Bar
  const pct = total > 0 ? Math.min(100, Math.round(((created + failed) / total) * 100)) : 0;
  document.getElementById('progressBar').style.width = `${pct}%`;
}

function renderCreatedThreads(threads) {
  const wrap = document.getElementById('createdThreadsWrap');
  const list = document.getElementById('createdThreadsList');

  if (!threads || threads.length === 0) {
    wrap.style.display = 'none';
    return;
  }

  wrap.style.display = 'block';
  list.innerHTML = '';

  threads.forEach(t => {
    const chip = document.createElement('div');
    chip.className = 'thread-chip';
    chip.innerHTML = `
      <span class="t-num">#${t.gc_num}</span>
      <span class="t-name">${escapeHtml(t.name)}</span>
      <span class="t-id">ID: ${escapeHtml(t.thread_id)}</span>
      <button class="btn-icon-small" onclick="copyText('${escapeHtml(t.thread_id)}')">📋</button>
    `;
    list.appendChild(chip);
  });
}

// --- SESSIONS MANAGEMENT ---
async function loadSessions() {
  const container = document.getElementById('sessionList');
  try {
    const res = await fetch('/api/sessions', {
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();

    if (data.success) {
      savedSessionsMap = data.sessions || {};
      renderSessionsList();
    }
  } catch (err) {
    container.innerHTML = '<div class="term-error">Failed to load sessions</div>';
  }
}

function renderSessionsList() {
  const container = document.getElementById('sessionList');
  container.innerHTML = '';

  const labels = Object.keys(savedSessionsMap);

  if (labels.length === 0) {
    container.innerHTML = `
      <div style="padding: 14px; text-align: center; color: var(--text-muted);">
        No saved Instagram sessions found. Click <b>"➕ ADD NEW SESSION"</b> to add your first session cookie.
      </div>
    `;
    selectedSessionLabel = null;
    document.getElementById('currentSelectedSessionLabel').textContent = 'None Selected';
    return;
  }

  labels.forEach((label, idx) => {
    const isSelected = selectedSessionLabel ? selectedSessionLabel === label : idx === 0;
    if (isSelected) selectedSessionLabel = label;

    const item = document.createElement('div');
    item.className = `session-item ${isSelected ? 'selected' : ''}`;
    item.onclick = () => selectSession(label);

    const maskedSid = savedSessionsMap[label].substring(0, 16) + '...';

    item.innerHTML = `
      <div class="session-left">
        <input type="radio" name="sessionRadio" class="session-radio" ${isSelected ? 'checked' : ''}>
        <div class="session-info">
          <div class="s-label">🔱 [${idx + 1}] ${escapeHtml(label)}</div>
          <div class="s-preview">${escapeHtml(maskedSid)}</div>
        </div>
      </div>
      <div class="session-actions">
        <button type="button" class="btn-icon-small" onclick="event.stopPropagation(); deleteSession('${escapeHtml(label)}')" title="Delete Session">🗑️</button>
      </div>
    `;
    container.appendChild(item);
  });

  document.getElementById('currentSelectedSessionLabel').textContent = selectedSessionLabel ? `✅ ${selectedSessionLabel}` : 'None Selected';
}

function selectSession(label) {
  selectedSessionLabel = label;
  renderSessionsList();
}

async function handleSaveSession(e) {
  e.preventDefault();
  const label = document.getElementById('newSessionLabel').value.trim();
  const sessionid = document.getElementById('newSessionId').value.trim();

  if (!label || !sessionid) {
    showToast('Please provide both label and session ID', 'warn');
    return;
  }

  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({ label, sessionid })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeModal('modalAddSession');
      document.getElementById('newSessionLabel').value = '';
      document.getElementById('newSessionId').value = '';
      selectedSessionLabel = label;
      loadSessions();
    } else {
      showToast(data.message || 'Error saving session', 'error');
    }
  } catch (err) {
    showToast('Network error while saving session', 'error');
  }
}

async function deleteSession(label) {
  if (!confirm(`Are you sure you want to delete session '${label}'?`)) return;

  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(label)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Session '${label}' deleted`, 'info');
      if (selectedSessionLabel === label) selectedSessionLabel = null;
      loadSessions();
    } else {
      showToast(data.message || 'Error deleting session', 'error');
    }
  } catch (err) {
    showToast('Network error while deleting session', 'error');
  }
}

// --- GC CREATION FLOW ---
async function fetchInitialTaskStatus() {
  try {
    const res = await fetch('/api/tasks/status', {
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();
    if (data.success) {
      updateTaskStatus(data.status);
      updateStatsDisplay(data.stats);
      if (data.created_gcs) renderCreatedThreads(data.created_gcs);
    }
  } catch (e) {
    console.warn('Initial status fetch error:', e);
  }
}

async function handleStartCreation(e) {
  e.preventDefault();

  if (!selectedSessionLabel || !savedSessionsMap[selectedSessionLabel]) {
    showToast('Please select or add an Instagram session first!', 'warn');
    return;
  }

  const gcCount = parseInt(document.getElementById('gcCount').value) || 1;
  const gcName = document.getElementById('gcName').value.trim();
  const rawMembers = document.getElementById('gcMembers').value.trim();
  const delayBetween = parseInt(document.getElementById('delayBetween').value) || 5;
  const isHeadless = document.getElementById('headlessMode').checked;

  const members = rawMembers.split(',').map(u => u.trim().replace(/^@/, '')).filter(Boolean);

  if (members.length < 2) {
    showToast('At least 2 member usernames required to form a group!', 'warn');
    return;
  }

  const payload = {
    session_label: selectedSessionLabel,
    session_id: savedSessionsMap[selectedSessionLabel],
    gc_count: gcCount,
    gc_name: gcName,
    members: members,
    delay_between: delayBetween,
    headless: isHeadless
  };

  try {
    const res = await fetch('/api/tasks/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (data.success) {
      showToast('🚀 GC Creator process launched!', 'success');
      updateTaskStatus('running');
    } else {
      showToast(data.message || 'Failed to start task', 'error');
    }
  } catch (err) {
    showToast('Network error while starting GC creator', 'error');
  }
}

async function handleStopCreation() {
  if (!confirm('Are you sure you want to STOP the running GC Creation process?')) return;

  try {
    const res = await fetch('/api/tasks/stop', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      }
    });
    const data = await res.json();
    if (data.success) {
      showToast('🛑 Stop signal sent!', 'info');
      updateTaskStatus('stopped');
    } else {
      showToast(data.message || 'Error stopping task', 'error');
    }
  } catch (err) {
    showToast('Network error while stopping task', 'error');
  }
}

function stepCount(delta) {
  const input = document.getElementById('gcCount');
  let val = parseInt(input.value) || 1;
  val = Math.max(1, Math.min(100, val + delta));
  input.value = val;
}

// --- OWNER FEATURES: USER MANAGEMENT ---
function switchOwnerTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

  if (tab === 'creator') {
    document.querySelector('.tab-btn:nth-child(1)').classList.add('active');
    document.getElementById('tabCreator').classList.add('active');
  } else if (tab === 'users') {
    document.querySelector('.tab-btn:nth-child(2)').classList.add('active');
    document.getElementById('tabUsers').classList.add('active');
    fetchUsersList();
  }
}

async function fetchUsersList() {
  const tbody = document.getElementById('usersTableBody');
  try {
    const res = await fetch('/api/admin/users', {
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();

    if (data.success) {
      tbody.innerHTML = '';
      data.users.forEach(u => {
        const tr = document.createElement('tr');
        const isOwnerAcc = u.username === 'OWNER' || u.username === 'PRINCE';

        tr.innerHTML = `
          <td><b>${escapeHtml(u.username)}</b></td>
          <td>
            <span class="password-masked" id="pwd_${escapeHtml(u.username)}" data-pwd="${escapeHtml(u.password)}">••••••••</span>
            <button type="button" class="btn-icon-small" onclick="toggleTablePassword('pwd_${escapeHtml(u.username)}', this)" title="Show/Hide Password">👁️</button>
          </td>
          <td><span class="badge-role ${u.role === 'owner' ? 'owner' : ''}">${u.role.toUpperCase()}</span></td>
          <td>${escapeHtml(u.created_at || 'N/A')}</td>
          <td>
            <div class="table-actions">
              <button class="btn-small btn-edit" onclick="openEditUserModal('${escapeHtml(u.username)}', '${escapeHtml(u.password)}', '${escapeHtml(u.role)}')">✏️ EDIT</button>
              ${!isOwnerAcc ? `<button class="btn-small btn-delete" onclick="deleteUser('${escapeHtml(u.username)}')">🗑️ DELETE</button>` : ''}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="term-error">Error fetching users list</td></tr>`;
  }
}

async function handleAddUserSubmit(e) {
  e.preventDefault();
  const username = document.getElementById('newUsername').value.trim();
  const password = document.getElementById('newUserPassword').value.trim();
  const role = document.getElementById('newUserRole').value;

  try {
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({ username, password, role })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeModal('modalAddUser');
      fetchUsersList();
    } else {
      showToast(data.message || 'Error adding user', 'error');
    }
  } catch (err) {
    showToast('Network error while adding user', 'error');
  }
}

function openEditUserModal(username, password, role) {
  document.getElementById('editOriginalUsername').value = username;
  document.getElementById('editUsername').value = username;
  document.getElementById('editPassword').value = password;
  document.getElementById('editRole').value = role;
  openModal('modalEditUser');
}

async function handleEditUserSubmit(e) {
  e.preventDefault();
  const original_username = document.getElementById('editOriginalUsername').value;
  const username = document.getElementById('editUsername').value.trim();
  const password = document.getElementById('editPassword').value.trim();
  const role = document.getElementById('editRole').value;

  try {
    const res = await fetch('/api/admin/users', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({ original_username, username, password, role })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      closeModal('modalEditUser');
      fetchUsersList();
    } else {
      showToast(data.message || 'Error updating user', 'error');
    }
  } catch (err) {
    showToast('Network error while editing user', 'error');
  }
}

async function deleteUser(username) {
  if (!confirm(`Delete user '${username}' permanently?`)) return;

  try {
    const res = await fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      fetchUsersList();
    } else {
      showToast(data.message || 'Error deleting user', 'error');
    }
  } catch (err) {
    showToast('Network error while deleting user', 'error');
  }
}

// --- OWNER FEATURES: LIVE MONITOR ---
async function fetchLiveMonitor() {
  const container = document.getElementById('ownerMonitorGrid');
  try {
    const res = await fetch('/api/admin/live_monitor', {
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();

    if (data.success) {
      container.innerHTML = '';
      if (!data.monitor || data.monitor.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted);">No active users running currently.</div>';
        return;
      }

      data.monitor.forEach(m => {
        const isRunning = m.status === 'running';
        const card = document.createElement('div');
        card.className = 'monitor-user-card';
        card.innerHTML = `
          <div class="monitor-card-header">
            <div class="monitor-uname">👤 ${escapeHtml(m.username)}</div>
            <span class="badge-status badge-${m.status}">${m.status.toUpperCase()}</span>
          </div>
          <div class="monitor-stats-row">
            <span>GC Created: <b style="color:var(--green)">${m.stats.created || 0}</b> / ${m.stats.total || 0}</span>
            <span>Started: ${escapeHtml(m.start_time || 'N/A')}</span>
          </div>
          <div class="monitor-recent-log" title="${escapeHtml(m.recent_log)}">
            ${escapeHtml(m.recent_log)}
          </div>
          ${isRunning ? `
            <button class="btn-3d btn-danger btn-small" onclick="ownerForceStop('${escapeHtml(m.username)}')">
              🛑 FORCE STOP USER
            </button>
          ` : ''}
        `;
        container.appendChild(card);
      });
    }
  } catch (err) {
    container.innerHTML = `<div class="term-error">Error fetching live monitor</div>`;
  }
}

async function ownerForceStop(target_user) {
  if (!confirm(`Force STOP GC creation task for user '${target_user}'?`)) return;

  try {
    const res = await fetch('/api/tasks/stop', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
      },
      body: JSON.stringify({ target_user })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Stopped task for ${target_user}`, 'info');
      fetchLiveMonitor();
    }
  } catch (err) {
    showToast('Network error stopping user task', 'error');
  }
}

// --- MODALS & UTILS ---
function openModal(id) {
  document.getElementById(id).classList.add('active');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}
function openAddSessionModal() { openModal('modalAddSession'); }
function openAddUserModal() { openModal('modalAddUser'); }

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warn' ? '⚠️' : '⚡';
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy', 'error');
  });
}

function copyBanner() {
  const banner = document.getElementById('asciiBanner').innerText;
  copyText(banner);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
