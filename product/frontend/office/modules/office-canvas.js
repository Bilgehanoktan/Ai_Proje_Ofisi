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

export function createOfficeCanvas(canvasEl, hotspotsEl, { onSelectRole }) {
  const ctx = canvasEl.getContext('2d');
  ctx.imageSmoothingEnabled = false;

  const rect = (x, y, w, h, color) => {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  };

  const text = (label, x, y, size = 13, color = '#40555b', bold = false) => {
    ctx.fillStyle = color;
    ctx.font = `${bold ? '600' : '400'} ${size}px Segoe UI`;
    ctx.fillText(label, x, y);
  };

  const line = (x, y, x2, y2, color, width = 2) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  };

  const wall = (x, y, w, h) => {
    rect(x, y, w, h, '#839799');
    rect(x, y, w, 5, '#c0cdca');
    rect(x, y + h - 5, w, 5, '#627b7f');
  };

  const desk = (x, y, color = '#bea17b') => {
    rect(x + 4, y + 12, 110, 51, '#00000017');
    rect(x + 8, y + 38, 7, 25, '#8a775e');
    rect(x + 94, y + 38, 7, 25, '#8a775e');
    rect(x, y, 110, 45, '#927955');
    rect(x, y, 110, 35, color);
    rect(x + 37, y - 19, 40, 28, '#344d55');
    rect(x + 41, y - 15, 32, 19, '#94babb');
    rect(x + 53, y + 9, 10, 5, '#536a71');
    rect(x + 39, y + 20, 34, 6, '#e4e6d8');
    rect(x + 10, y + 8, 17, 14, '#f4f0dc');
    line(x + 13, y + 12, x + 23, y + 12, '#a8b1a2', 1);
    rect(x + 87, y + 9, 9, 11, '#f2e9d1');
    rect(x + 89, y + 7, 5, 3, '#f2e9d1');
  };

  const chair = (x, y) => {
    rect(x + 4, y + 14, 36, 15, '#536b6d');
    rect(x, y, 44, 24, '#6e8788');
    rect(x + 3, y + 3, 38, 7, '#91a7a3');
    rect(x + 19, y + 29, 5, 9, '#435a61');
    rect(x + 5, y + 37, 33, 3, '#435a61');
  };

  const person = (x, y, color) => {
    rect(x - 15, y + 15, 34, 5, '#00000016');
    rect(x - 10, y - 8, 21, 22, color);
    rect(x - 15, y - 5, 5, 17, color);
    rect(x + 11, y - 5, 5, 17, color);
    rect(x - 9, y + 14, 7, 13, '#3d515b');
    rect(x + 4, y + 14, 7, 13, '#3d515b');
    rect(x - 11, y + 26, 10, 4, '#2e414b');
    rect(x + 4, y + 26, 10, 4, '#2e414b');
    rect(x - 8, y - 28, 18, 21, '#d4ad89');
    rect(x - 10, y - 30, 22, 8, '#5f5148');
    rect(x - 10, y - 23, 4, 8, '#5f5148');
    rect(x - 3, y - 18, 3, 3, '#4d4943');
    rect(x + 6, y - 18, 3, 3, '#4d4943');
  };

  const plant = (x, y) => {
    rect(x - 10, y + 10, 23, 22, '#b08d71');
    rect(x - 13, y + 7, 29, 8, '#ceb08c');
    rect(x - 3, y - 20, 5, 30, '#68846a');
    rect(x - 18, y - 14, 17, 10, '#799679');
    rect(x + 2, y - 25, 18, 12, '#638a75');
    rect(x - 13, y - 33, 14, 15, '#8faa83');
    rect(x + 4, y - 7, 17, 9, '#8faa83');
  };

  const plaque = (label, x, y, w, color) => {
    rect(x, y, w, 29, '#ffffffd9');
    rect(x, y, 4, 29, color);
    text(label, x + 12, y + 19, 13, '#3b535b', true);
  };

  const windowArt = (x, y, w) => {
    rect(x, y, w, 35, '#678a94');
    rect(x + 5, y + 4, w - 10, 25, '#bfd8dc');
    rect(x + w / 2, y + 4, 4, 25, '#739aa2');
    rect(x - 3, y + 32, w + 6, 7, '#dfe8df');
  };

  function drawBaseScene() {
    rect(0, 0, 1100, 720, '#d1dddf');
    rect(44, 54, 1020, 625, '#b7c5c5');
    rect(37, 44, 1020, 625, '#8c9b9e');
    rect(47, 54, 1000, 603, '#d6c5a5');
    for (let y = 63; y < 656; y += 28) {
      line(49, y, 1045, y, '#c8b799', 1);
      for (let x = 50 + (Math.floor(y / 28) % 2) * 60; x < 1040; x += 120) {
        line(x, y, x, y + 28, '#c8b799', 1);
      }
    }
    wall(37, 28, 1020, 37);
    wall(37, 28, 12, 627);
    wall(1045, 28, 12, 627);
    windowArt(104, 29, 145);
    windowArt(476, 29, 145);
    windowArt(824, 29, 145);
    rect(65, 84, 281, 238, '#d2dfca');
    rect(369, 84, 361, 238, '#d3dde1');
    rect(751, 84, 273, 238, '#e4d7be');
    plaque('Research', 79, 94, 139, '#799a8b');
    plaque('Orchestrator', 392, 94, 164, '#788eaa');
    plaque('Engineer', 773, 94, 140, '#b79368');
    wall(348, 84, 9, 191);
    wall(738, 84, 9, 191);
    wall(67, 321, 121, 17);
    wall(270, 321, 77, 17);
    wall(752, 321, 82, 17);
    wall(918, 321, 106, 17);
    desk(149, 196);
    chair(183, 257);
    person(204, 263, '#6d947e');
    desk(498, 196, '#adbbbf');
    chair(530, 257);
    person(550, 263, '#6e87ab');
    desk(829, 196);
    chair(862, 257);
    person(882, 263, '#bb8a58');
    plant(87, 267);
    plant(1000, 267);
    text('Ortak geçiş', 465, 371, 12, '#867e6b');
    rect(64, 409, 282, 207, '#d9ddd0');
    plaque('Pasif rezerv', 80, 425, 157, '#a6ae9b');
    ctx.setLineDash([7, 6]);
    ctx.strokeStyle = '#a5af9d';
    ctx.strokeRect(89, 480, 229, 98);
    ctx.setLineDash([]);
    text('Boş büyüme alanı', 132, 527, 14, '#84917e');
    text('Yeni ajan yerleştirilmedi', 119, 551, 11, '#84917e');
    rect(371, 410, 360, 207, '#dfd5bf');
    plaque('Briefing / giriş', 390, 425, 168, '#9b967d');
    rect(469, 498, 163, 62, '#ab906f');
    rect(464, 488, 163, 58, '#c9b18a');
    rect(479, 479, 32, 12, '#7e9390');
    rect(576, 479, 32, 12, '#7e9390');
    rect(479, 551, 32, 12, '#7e9390');
    rect(576, 551, 32, 12, '#7e9390');
    rect(516, 504, 28, 21, '#f2f1df');
    rect(555, 507, 24, 16, '#d6e1de');
    plant(402, 566);
    rect(751, 411, 273, 206, '#e1dce6');
    wall(741, 402, 13, 213);
    wall(751, 400, 79, 28);
    wall(919, 400, 114, 28);
    plaque('QA / kontrol', 773, 439, 153, '#978ba5');
    desk(830, 515, '#b9afc1');
    chair(863, 571);
    person(884, 577, '#9482a6');
    wall(751, 617, 273, 14);
    rect(78, 641, 182, 18, '#879697');
    text('Kat geçişi · Kapalı', 99, 654, 11, '#f1f4ed');
    rect(476, 640, 151, 19, '#a5ada4');
    text('Giriş', 534, 654, 11, '#465c59');
    plant(998, 580);
    text('Örnek figürler · Canlı çalışma gösterilmez', 745, 686, 12, '#617981');
  }

  function drawActiveMarkers(agents = [], runs = [], footerText = '') {
    const activeAgents = agents.filter(
      (a) => a.state === 'RUNNING' || a.state === 'BLOCKED' || a.state === 'STALE',
    );
    if (activeAgents.length) {
      activeAgents.forEach((a, idx) => {
        const r = ROLES[ROLE_ID_TO_SCENE_KEY[a.role_id] || 'engineer'];
        if (!r) return;
        const bg = a.state === 'RUNNING' ? '#215246' : (a.state === 'BLOCKED' ? '#9b2c2c' : '#8a5a19');
        const lbl = a.state === 'RUNNING' ? `● ${a.display_name}` : `! ${a.display_name} (${a.state})`;
        rect(r.x + r.w - 146, r.y + 10 + idx * 26, 134, 22, bg);
        text(lbl.slice(0, 18), r.x + r.w - 138, r.y + 25 + idx * 26, 11, '#ffffff', true);
      });
    } else if (Array.isArray(runs)) {
      const running = runs.find((r) => r.state === 'RUNNING' || r.state === 'QUEUED');
      if (running) {
        const r = ROLES[ROLE_ID_TO_SCENE_KEY[running.role_id] || 'engineer'];
        if (r) {
          rect(r.x + r.w - 108, r.y + 10, 96, 24, '#215246');
          text('● Çalışıyor', r.x + r.w - 98, r.y + 26, 12, '#ffffff', true);
        }
      }
    }
    if (footerText) {
      rect(730, 668, 315, 24, '#d1dddf');
      text(footerText, 745, 686, 12, '#14532d', true);
    }
  }

  hotspotsEl.replaceChildren();
  Object.entries(ROLES).forEach(([key, r]) => {
    const btn = document.createElement('button');
    btn.className = 'hotspot';
    btn.dataset.role = key;
    btn.setAttribute('aria-label', `${r.name} örnek rolünü seç`);
    btn.setAttribute('aria-pressed', String(key === 'orchestrator'));
    Object.assign(btn.style, {
      left: `${r.x / 11}%`,
      top: `${r.y / 7.2}%`,
      width: `${r.w / 11}%`,
      height: `${r.h / 7.2}%`,
    });
    btn.addEventListener('click', () => onSelectRole(key));
    hotspotsEl.append(btn);
  });

  drawBaseScene();

  return {
    draw(agents = [], runs = [], footerText = '') {
      drawBaseScene();
      drawActiveMarkers(agents, runs, footerText);
    },
  };
}
