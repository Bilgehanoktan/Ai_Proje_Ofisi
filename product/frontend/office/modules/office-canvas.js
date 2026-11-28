import { mountPhaserFloor } from './phaser-scene.js';

export const ROLES = {
  research: {
    zoneId: 'F1-RSCH',
    name: 'Research',
    sub: 'Yarı açık araştırma alanı · F1-RSCH',
    description: 'Yetkili kaynakları inceler, araştırma bulgularını ve kaynak izlerini toplar.',
    icon: '⌕',
    x: 65,
    y: 84,
    w: 281,
    h: 238,
  },
  orchestrator: {
    zoneId: 'F1-ORCH',
    name: 'Orchestrator',
    sub: 'Merkez koordinasyon alanı · F1-ORCH',
    description: 'Planlama, delegasyon ve koordinasyon. İnsan sahibin hedefleri ve mevcut yetki sınırları esas alınır.',
    icon: '◇',
    x: 369,
    y: 84,
    w: 361,
    h: 238,
  },
  engineer: {
    zoneId: 'F1-ENG',
    name: 'Engineer',
    sub: 'Yarı açık üretim alanı · F1-ENG',
    description: 'Teknik üretim ve yazılım görevlerini izinli worker ve araç sınırlarında yürütür. İlk akış SOFTWARE MGT01’dir.',
    icon: '⌨',
    x: 751,
    y: 84,
    w: 273,
    h: 238,
  },
  qa: {
    zoneId: 'F1-QA',
    name: 'QA',
    sub: 'Ayrışmış, yarı kapalı kontrol alanı · F1-QA',
    description: 'Teknik inceleme ve kanıt toplama. QA rolü bağımsız Verifier veya insan kabulünün yerine geçmez.',
    icon: '✓',
    x: 751,
    y: 411,
    w: 273,
    h: 206,
  },
};

export const ROLE_ID_TO_SCENE_KEY = {
  'EXP-02': 'research',
  'MGR-01': 'orchestrator',
  'EXP-01': 'engineer',
  'QA-01': 'qa',
  'EXP-03': 'qa',
  'EXP-04': 'research',
};

export const SCENE_KEY_TO_ROLE_ID = {
  research: 'EXP-02',
  orchestrator: 'MGR-01',
  engineer: 'EXP-01',
  qa: 'QA-01',
};

const STATE_BADGE_MAP = {
  RUNNING: { sym: '●', text: 'Çalışıyor' },
  BLOCKED: { sym: '◆', text: 'Engelli' },
  STALE: { sym: '△', text: 'Güncel değil' },
  IDLE: { sym: '○', text: 'Boşta' },
};

export function createOfficeCanvas(canvasEl, hotspotsEl, { onSelectRole, onSelectAgent }) {
  const ctx = canvasEl.getContext('2d');
  const agentRows = new Map();
  let currentSelectedId = null;
  let sceneFilter = 'ALL';

  const palette = {
    research: ['#173b3a', '#79e1c9'],
    orchestrator: ['#1a3358', '#9cc6ff'],
    engineer: ['#3d302f', '#ffd1a0'],
    qa: ['#352b50', '#d7bdff'],
  };

  const phaserHost = document.createElement('div');
  phaserHost.className = 'phaser-floor';
  canvasEl.after(phaserHost);
  const phaser = mountPhaserFloor({
    floor: canvasEl,
    host: phaserHost,
    getCharacters: () =>
      Array.from(agentRows, ([key, row]) =>
        Array.from(row.querySelectorAll('.scene-agent'), (btn) => {
          const anchor = btn.querySelector('.scene-agent-avatar');
          return {
            anchor,
            color: Number.parseInt(palette[key][1].slice(1), 16),
            state: btn.dataset.agentState || 'IDLE',
            selected: btn.dataset.sceneAgentId === currentSelectedId,
          };
        }).filter((item) => Boolean(item.anchor)),
      ).flat(),
  });

  function box(x, y, width, height, radius, fill, border, lineWidth = 1) {
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, radius);
    ctx.fillStyle = fill;
    ctx.fill();
    if (border) {
      ctx.strokeStyle = border;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    }
  }

  function text(label, x, y, size, color, weight = 400, maxWidth = 1000) {
    ctx.fillStyle = color;
    ctx.font = `${weight} ${size}px "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(label, x, y, maxWidth);
  }

  function drawStationAccessory(key, role, accent) {
    const rx = role.x + role.w - 76;
    const ry = role.y + 22;
    if (key === 'research') {
      // Document / analysis shelf
      box(rx, ry, 52, 34, 6, '#0f292a', accent + '66');
      box(rx + 8, ry + 8, 36, 4, 2, accent + 'aa');
      box(rx + 8, ry + 16, 26, 4, 2, accent + '77');
      box(rx + 8, ry + 24, 32, 4, 2, accent + '55');
    } else if (key === 'orchestrator') {
      // Central delegation board
      box(rx - 8, ry, 60, 36, 6, '#102342', accent + '77');
      box(rx - 2, ry + 7, 14, 10, 2, '#fbbf24aa');
      box(rx + 16, ry + 7, 14, 10, 2, accent + '99');
      box(rx + 34, ry + 7, 12, 10, 2, '#34d399aa');
      box(rx - 2, ry + 21, 48, 8, 2, accent + '44');
    } else if (key === 'engineer') {
      // Dual-monitor console
      box(rx - 6, ry + 4, 26, 20, 4, '#231c1d', accent + '88');
      box(rx + 24, ry + 4, 26, 20, 4, '#231c1d', accent + '88');
      box(rx + 8, ry + 26, 28, 5, 2, accent + '66');
    } else if (key === 'qa') {
      // Verification & evidence screen
      box(rx, ry, 52, 34, 6, '#231b38', accent + '88');
      text('IV·QA', rx + 8, ry + 22, 13, accent, 700);
    }
  }

  function drawRoom(key, role, colors, count, runningCount) {
    const { x, y, w, h } = role;
    const [surface, accent] = colors;
    box(x + 4, y + 9, w, h, 16, '#080f1e');
    box(x, y + 5, w, h, 16, '#263950');
    box(
      x,
      y,
      w,
      h,
      16,
      surface,
      runningCount > 0 ? '#34d399aa' : accent + '55',
      runningCount > 0 ? 2 : 1,
    );
    box(x + 22, y + 20, 42, 42, 10, accent + '22');
    text(role.icon, x + 31, y + 49, 24, accent, 650);
    text(role.name, x + 74, y + 46, 24, '#f5f8ff', 650, w - 156);
    text(role.zoneId, x + 75, y + 64, 11, '#9fb5d5', 600);
    const subLabel =
      count === null
        ? 'Örnek çalışma alanı'
        : runningCount > 0
          ? `${count} ajan · ● ${runningCount} çalışıyor`
          : `${count} ajan kaydı`;
    text(subLabel, x + 23, y + 86, 15, runningCount > 0 ? '#6ee7b7' : accent, 600, w - 46);
    drawStationAccessory(key, role, accent);

    // Door portal indicator on corridor edge (DEC-28C §2.4)
    const doorX = x + Math.round(w / 2) - 22;
    const doorY = key === 'qa' ? y - 3 : y + h - 3;
    box(doorX, doorY, 44, 6, 3, '#38bdf8cc');
  }

  function matchesFilter(agent) {
    if (sceneFilter === 'RUNNING') return agent.state === 'RUNNING';
    if (sceneFilter === 'ATTENTION') return agent.state === 'BLOCKED' || agent.state === 'STALE';
    return true;
  }

  function renderRoomAgents(key, agents, selectedId) {
    const row = agentRows.get(key);
    const visible = agents.slice(0, 4);
    const signature = JSON.stringify(
      visible.map((agent) => [agent.agent_instance_id, agent.display_name, agent.state, sceneFilter]),
    );
    if (row.dataset.signature !== signature) {
      const focusedId = row.contains(document.activeElement)
        ? document.activeElement.dataset.sceneAgentId
        : null;
      row.replaceChildren();
      for (const agent of visible) {
        const badge = STATE_BADGE_MAP[agent.state] || STATE_BADGE_MAP.IDLE;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'scene-agent';
        button.dataset.sceneAgentId = agent.agent_instance_id;
        button.dataset.agentState = agent.state || 'IDLE';
        if (!matchesFilter(agent)) {
          button.classList.add('scene-agent-dimmed');
        }
        const avatar = document.createElement('span');
        avatar.className = 'scene-agent-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = agent.display_name
          .trim()
          .split(/\s+/)
          .slice(0, 2)
          .map((word) => word[0])
          .join('')
          .toLocaleUpperCase('tr-TR');
        const name = document.createElement('span');
        name.className = 'scene-agent-name';
        name.textContent = `${badge.sym} ${agent.display_name}${agent.state === 'RUNNING' ? ' · Çalışıyor' : agent.state === 'STALE' ? ' · STALE' : ''}`;
        button.title = `${agent.display_name} (${agent.role_id}) — ${badge.text}`;
        button.append(avatar, name);
        button.addEventListener('click', () => onSelectAgent(agent.agent_instance_id));
        row.append(button);
        if (agent.agent_instance_id === focusedId) button.focus({ preventScroll: true });
      }
      row.dataset.signature = signature;
    }
    for (const button of row.children) {
      button.setAttribute('aria-pressed', String(button.dataset.sceneAgentId === selectedId));
    }
  }

  function drawScene(agents = null, footerText = '', selectedId = null) {
    currentSelectedId = selectedId;
    const background = ctx.createLinearGradient(0, 0, 1100, 720);
    background.addColorStop(0, '#13263f');
    background.addColorStop(1, '#0a1426');
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, 1100, 720);

    ctx.fillStyle = '#97b7e220';
    for (let y = 16; y < 720; y += 24) {
      for (let x = 16; x < 1100; x += 24) ctx.fillRect(x, y, 1.5, 1.5);
    }

    // Floor shell + North wall elevation + 3 architectural windows (DEC-28C §3)
    box(42, 48, 1004, 604, 24, '#101c30', '#354560');
    box(42, 48, 1004, 24, 12, '#1e324d', '#476184');
    for (const wx of [135, 478, 815]) {
      box(wx, 52, 136, 14, 4, '#7dd3fc44', '#93c5fd88');
    }

    // Main horizontal walkable corridor (F1-COR) & vertical connectors (F1-VL / F1-VR)
    box(58, 336, 972, 60, 10, '#15263d', '#2b4260');
    box(350, 84, 15, 533, 4, '#15263d');
    box(733, 84, 14, 533, 4, '#15263d');
    text('ANA KORİDOR · F1-COR (Ortak Geçiş)', 428, 372, 14, '#9fb5d5', 600);

    for (const [key, role] of Object.entries(ROLES)) {
      const roomAgents = agents?.filter((agent) => ROLE_ID_TO_SCENE_KEY[agent.role_id] === key);
      const runningCount = roomAgents
        ? roomAgents.filter((agent) => agent.state === 'RUNNING').length
        : 0;
      drawRoom(key, role, palette[key], roomAgents?.length ?? null, runningCount);
      renderRoomAgents(key, roomAgents ?? [], selectedId);
    }

    // Passive Reserve (F1-EXP — closed door)
    box(65, 411, 281, 206, 16, '#142235', '#35455c');
    box(183, 408, 44, 6, 3, '#ef4444aa');
    text('Pasif rezerv', 88, 462, 23, '#d8e4f4', 600);
    text('F1-EXP · 2–4 istasyon adayı (Kapalı)', 88, 490, 14, '#9caec9');
    ctx.setLineDash([6, 6]);
    box(88, 514, 110, 42, 8, '#142235', '#637896');
    box(210, 514, 110, 42, 8, '#142235', '#637896');
    ctx.setLineDash([]);
    text('Hayalet ajan yok', 88, 584, 13, '#7b90b0');

    // Briefing / Entrance (F1-BRIEF)
    box(369, 411, 361, 206, 16, '#1a2a40', '#405777');
    box(527, 408, 44, 6, 3, '#38bdf8cc');
    text('Briefing / giriş', 392, 460, 23, '#e3edff', 600);
    text('F1-BRIEF · Ortak toplantı & giriş aksı', 392, 486, 13, '#9fb5d5');
    box(459, 523, 182, 50, 25, '#2d4567', '#6885ae');
    for (const center of [490, 550, 610]) {
      box(center - 11, 511, 22, 9, 4, '#9fb5d5');
      box(center - 11, 577, 22, 9, 4, '#9fb5d5');
    }

    // South Entry & Disabled Upper Floor Portal (DEC-28C §2.4)
    box(492, 636, 116, 22, 6, '#1e3a5f', '#60a5faaa');
    text('↓ ANA GİRİŞ', 509, 652, 12, '#dbeafe', 600);
    box(808, 636, 216, 22, 6, '#1c2738', '#475569');
    text('Kat Portali (Kat 02+ · Kapalı)', 824, 652, 12, '#94a3b8', 600);

    text(footerText || 'Kat 01 · F1-DEC28C (Taslak Yerleşim)', 65, 690, 15, '#b5c5df');
    text('Görsel durum yetki üretmez (MOD-011)', 790, 690, 14, '#94a3b8');
    phaser.refresh();
  }

  function setFilter(nextFilter, agents, footerText, selectedId) {
    sceneFilter = nextFilter || 'ALL';
    drawScene(agents, footerText, selectedId);
  }

  function focusRoleRoom(sceneKey) {
    const btn = hotspotsEl.querySelector(`.hotspot[data-role="${sceneKey}"]`);
    if (btn) {
      btn.scrollIntoView({ behavior: phaser.getReducedMotion() ? 'auto' : 'smooth', block: 'nearest', inline: 'center' });
    }
  }

  hotspotsEl.replaceChildren();
  Object.entries(ROLES).forEach(([key, r]) => {
    const btn = document.createElement('button');
    btn.className = 'hotspot';
    btn.dataset.role = key;
    btn.setAttribute('aria-label', `${r.name} (${r.zoneId}) alanını seç`);
    btn.setAttribute('aria-pressed', String(key === 'orchestrator'));
    Object.assign(btn.style, {
      left: `${r.x / 11}%`,
      top: `${r.y / 7.2}%`,
      width: `${r.w / 11}%`,
      height: `${r.h / 7.2}%`,
    });
    btn.addEventListener('click', () => onSelectRole(key));
    hotspotsEl.append(btn);
    const row = document.createElement('div');
    row.className = 'scene-agent-row';
    Object.assign(row.style, {
      left: `${(r.x + 22) / 11}%`,
      top: `${(r.y + 102) / 7.2}%`,
      width: `${(r.w - 44) / 11}%`,
    });
    row.style.setProperty('--agent-accent', palette[key][1]);
    hotspotsEl.append(row);
    agentRows.set(key, row);
  });

  drawScene();

  return {
    draw: drawScene,
    setFilter,
    focusRoleRoom,
    setReducedMotion: phaser.setReducedMotion,
    getReducedMotion: phaser.getReducedMotion,
  };
}
