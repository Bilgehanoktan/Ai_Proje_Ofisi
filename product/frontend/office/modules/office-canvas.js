import { mountPhaserFloor } from './phaser-scene.js';

export const ROLES = {
  research: {
    name: 'Research',
    sub: 'Yarı açık araştırma alanı',
    description: 'Yetkili kaynakları inceler, araştırma bulgularını ve kaynak izlerini toplar.',
    icon: '⌕',
    x: 65,
    y: 84,
    w: 281,
    h: 238,
  },
  orchestrator: {
    name: 'Orchestrator',
    sub: 'Merkez koordinasyon alanı',
    description: 'Planlama, delegasyon ve koordinasyon. İnsan sahibin hedefleri ve mevcut yetki sınırları esas alınır.',
    icon: '◇',
    x: 369,
    y: 84,
    w: 361,
    h: 238,
  },
  engineer: {
    name: 'Engineer',
    sub: 'Yarı açık üretim alanı',
    description: 'Teknik üretim ve yazılım görevlerini izinli worker ve araç sınırlarında yürütür. Bu projede ilk akış SOFTWARE MGT01’dir.',
    icon: '⌨',
    x: 751,
    y: 84,
    w: 273,
    h: 238,
  },
  qa: {
    name: 'QA',
    sub: 'Ayrışmış, yarı kapalı kontrol alanı',
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
};

export const SCENE_KEY_TO_ROLE_ID = {
  research: 'EXP-02',
  orchestrator: 'MGR-01',
  engineer: 'EXP-01',
  qa: 'QA-01',
};

export function createOfficeCanvas(canvasEl, hotspotsEl, { onSelectRole, onSelectAgent }) {
  const ctx = canvasEl.getContext('2d');
  const agentRows = new Map();
  const phaserHost = document.createElement('div');
  phaserHost.className = 'phaser-floor';
  canvasEl.after(phaserHost);
  const phaser = mountPhaserFloor({
    floor: canvasEl,
    host: phaserHost,
    getCharacters: () => Array.from(agentRows, ([key, row]) =>
      Array.from(row.querySelectorAll('.scene-agent-avatar'), (anchor) => ({
        anchor,
        color: Number.parseInt(palette[key][1].slice(1), 16),
      }))
    ).flat(),
  });
  const palette = {
    research: ['#173b3a', '#79e1c9'],
    orchestrator: ['#1a3358', '#9cc6ff'],
    engineer: ['#3d302f', '#ffd1a0'],
    qa: ['#352b50', '#d7bdff'],
  };

  function box(x, y, width, height, radius, fill, border) {
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, radius);
    ctx.fillStyle = fill;
    ctx.fill();
    if (border) {
      ctx.strokeStyle = border;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  function text(label, x, y, size, color, weight = 400, maxWidth = 1000) {
    ctx.fillStyle = color;
    ctx.font = `${weight} ${size}px "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(label, x, y, maxWidth);
  }

  function drawRoom(role, colors, count) {
    const { x, y, w, h } = role;
    const [surface, accent] = colors;
    box(x + 4, y + 9, w, h, 16, '#080f1e');
    box(x, y + 5, w, h, 16, '#263950');
    box(x, y, w, h, 16, surface, accent + '50');
    box(x + 22, y + 20, 42, 42, 10, accent + '22');
    text(role.icon, x + 31, y + 49, 24, accent, 650);
    text(role.name, x + 76, y + 48, 26, '#f5f8ff', 650, w - 94);
    text(count === null ? 'Örnek çalışma alanı' : `${count} ajan kaydı`,
      x + 23, y + 84, 17, accent, 600, w - 46);
  }

  function renderRoomAgents(key, agents, selectedId) {
    const row = agentRows.get(key);
    const visible = agents.slice(0, 4);
    const signature = JSON.stringify(visible.map((agent) => [agent.agent_instance_id, agent.display_name, agent.state]));
    if (row.dataset.signature !== signature) {
      const focusedId = row.contains(document.activeElement) ? document.activeElement.dataset.sceneAgentId : null;
      row.replaceChildren();
      for (const agent of visible) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'scene-agent';
        button.dataset.sceneAgentId = agent.agent_instance_id;
        const avatar = document.createElement('span');
        avatar.className = 'scene-agent-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = agent.display_name.trim().split(/\s+/).slice(0, 2)
          .map((word) => word[0]).join('').toLocaleUpperCase('tr-TR');
        const name = document.createElement('span');
        name.className = 'scene-agent-name';
        const status = { RUNNING: 'Çalışıyor', STALE: 'Güncel değil' }[agent.state];
        name.textContent = status ? `${agent.display_name} · ${status}` : agent.display_name;
        button.title = name.textContent;
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
    const background = ctx.createLinearGradient(0, 0, 1100, 720);
    background.addColorStop(0, '#13263f');
    background.addColorStop(1, '#0a1426');
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, 1100, 720);

    ctx.fillStyle = '#97b7e224';
    for (let y = 16; y < 720; y += 24) {
      for (let x = 16; x < 1100; x += 24) ctx.fillRect(x, y, 1.5, 1.5);
    }
    box(42, 61, 1004, 586, 28, '#101c30', '#354560');

    for (const [key, role] of Object.entries(ROLES)) {
      const roomAgents = agents?.filter((agent) => ROLE_ID_TO_SCENE_KEY[agent.role_id] === key);
      drawRoom(role, palette[key], roomAgents?.length ?? null);
      renderRoomAgents(key, roomAgents ?? [], selectedId);
    }

    box(65, 411, 281, 206, 16, '#142235', '#35455c');
    text('Pasif rezerv', 88, 479, 26, '#d8e4f4', 600);
    text('Yerleşim kapalı', 88, 514, 17, '#9caec9');
    ctx.setLineDash([6, 6]);
    box(89, 548, 230, 37, 8, '#142235', '#637896');
    ctx.setLineDash([]);

    box(369, 411, 361, 206, 16, '#1a2a40', '#405777');
    text('Briefing / giriş', 392, 479, 26, '#e3edff', 600);
    box(459, 521, 182, 54, 27, '#2d4567', '#6885ae');
    for (const center of [490, 550, 610]) {
      box(center - 11, 510, 22, 9, 4, '#9fb5d5');
      box(center - 11, 577, 22, 9, 4, '#9fb5d5');
    }

    text('Ortak geçiş', 486, 373, 17, '#b5c5df', 500);
    text(footerText || 'Tasarım önizlemesi', 65, 686, 17, '#b5c5df');
    text('Kat geçişi kapalı', 874, 686, 17, '#b5c5df');
    phaser.refresh();
  }

  hotspotsEl.replaceChildren();
  Object.entries(ROLES).forEach(([key, r]) => {
    const btn = document.createElement('button');
    btn.className = 'hotspot';
    btn.dataset.role = key;
    btn.setAttribute('aria-label', `${r.name} alanını seç`);
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
      top: `${(r.y + 99) / 7.2}%`,
      width: `${(r.w - 44) / 11}%`,
    });
    row.style.setProperty('--agent-accent', palette[key][1]);
    hotspotsEl.append(row);
    agentRows.set(key, row);
  });

  drawScene();

  return { draw: drawScene };
}
