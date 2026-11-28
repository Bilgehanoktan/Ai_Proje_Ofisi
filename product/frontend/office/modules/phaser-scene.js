import { fetchOfficeSnapshot, observeOfficeAgents } from './api-client.js';

export function mountPhaserFloor({ floor, host, getCharacters }) {
  let scene;
  let reducedMotion =
    typeof window !== 'undefined' &&
    Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

  function refresh() {
    if (!scene) return;
    const bounds = floor.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const scaleX = floor.width / bounds.width;
    const scaleY = floor.height / bounds.height;
    const art = scene.characterArt;
    art.clear();
    for (const { anchor, color, state, selected } of getCharacters()) {
      const rect = anchor.getBoundingClientRect();
      const x = Math.round((rect.left + rect.width / 2 - bounds.left) * scaleX);
      const y = Math.round((rect.top + rect.height / 2 - bounds.top) * scaleY);
      const size = Math.min(52, rect.height * scaleY);
      const pixel = Math.max(1, Math.floor(size / 12));
      const tile = (dx, dy, w, h, fill) =>
        art.fillStyle(fill).fillRect(x + dx * pixel, y + dy * pixel, w * pixel, h * pixel);

      // Layer 6: Selection contour (DEC-28C §3)
      if (selected) {
        art.lineStyle(2, 0xfbbf24, 0.95).strokeCircle(x, y, 8 * pixel);
      }

      // Layer 3/4: Shadow + 2.5D pixel figure
      art.fillStyle(0x080d18, 0.78).fillEllipse(x, y + 6 * pixel, 11 * pixel, 4 * pixel);
      tile(-3, 3, 2, 3, 0x273851);
      tile(1, 3, 2, 3, 0x273851);
      tile(-4, -1, 8, 5, state === 'STALE' ? 0x64748b : color);
      tile(-3, -5, 6, 5, 0xf4c69c);
      tile(-3, -6, 6, 2, 0x283043);
      tile(-2, -3, 1, 1, 0x283043);
      tile(1, -3, 1, 1, 0x283043);
      tile(-5, 0, 1, 3, 0xf4c69c);
      tile(4, 0, 1, 3, 0xf4c69c);

      // Layer 6: Non-color-only state badge overhead (DEC-28C §5 & §10)
      if (state === 'RUNNING') {
        art.fillStyle(0x10b981, 1).fillCircle(x + 5 * pixel, y - 6 * pixel, 2 * pixel);
        if (!reducedMotion) {
          art.lineStyle(1, 0x6ee7b7, 0.85).strokeCircle(x + 5 * pixel, y - 6 * pixel, 3.2 * pixel);
        }
      } else if (state === 'BLOCKED') {
        art.fillStyle(0xef4444, 1).fillRect(x + 4 * pixel, y - 7 * pixel, 2.5 * pixel, 2.5 * pixel);
      } else if (state === 'STALE') {
        art.lineStyle(1.5, 0x94a3b8, 0.9).strokeCircle(x + 5 * pixel, y - 6 * pixel, 2 * pixel);
      }
    }
  }

  function setReducedMotion(flag) {
    reducedMotion = Boolean(flag);
    refresh();
  }

  function start() {
    const Phaser = window.Phaser;
    if (!Phaser) return;
    new Phaser.Game({
      type: Phaser.CANVAS,
      parent: host,
      width: floor.width,
      height: floor.height,
      pixelArt: true,
      banner: false,
      audio: { noAudio: true },
      scene: {
        create() {
          this.textures.addCanvas('office-floor', floor);
          this.add.image(0, 0, 'office-floor').setOrigin(0, 0);
          this.characterArt = this.add.graphics();
          scene = this;
          host.dataset.ready = 'true';
          this.game.canvas.setAttribute('aria-hidden', 'true');
          const observer = new ResizeObserver(refresh);
          observer.observe(floor);
          this.events.once('shutdown', () => observer.disconnect());
          refresh();
        },
      },
    });
  }

  if (window.Phaser) {
    start();
  } else {
    const script = document.createElement('script');
    script.src = '/assets/vendor/phaser.min.js';
    script.addEventListener('load', start, { once: true });
    document.head.append(script);
  }

  return { refresh, setReducedMotion, getReducedMotion: () => reducedMotion };
}

const STATE_COLORS = {
  IDLE: 0x28665a,
  RUNNING: 0x2563eb,
  BLOCKED: 0xdc2626,
  STALE: 0x6b7280,
};

const STATE_SYMBOLS = {
  IDLE: '○',
  RUNNING: '●',
  BLOCKED: '◆',
  STALE: '△',
};

const ZONE_SLOTS = {
  research: { x: 135, y: 125, w: 230, h: 145, label: 'Research (F1-RSCH)', accent: 0x79e1c9 },
  orchestrator: { x: 430, y: 125, w: 230, h: 145, label: 'Orchestrator (F1-ORCH)', accent: 0x9cc6ff },
  engineer: { x: 725, y: 125, w: 230, h: 145, label: 'Engineer (F1-ENG)', accent: 0xffd1a0 },
  qa: { x: 725, y: 345, w: 230, h: 145, label: 'QA / Kontrol (F1-QA)', accent: 0xd7bdff },
};

const ROLE_TO_ZONE = {
  'EXP-02': 'research',
  'EXP-04': 'research',
  'MGR-01': 'orchestrator',
  'EXP-01': 'engineer',
  'QA-01': 'qa',
  'EXP-03': 'qa',
};

function drawPixelFigure(graphics, x, y, shirtColor, state) {
  const p = 3;
  const tile = (dx, dy, w, h, fill) =>
    graphics.fillStyle(fill).fillRect(x + dx * p, y + dy * p, w * p, h * p);
  graphics.fillStyle(0x0b1320, 0.75).fillEllipse(x, y + 6 * p, 11 * p, 4 * p);
  tile(-3, 3, 2, 3, 0x1e293b);
  tile(1, 3, 2, 3, 0x1e293b);
  tile(-4, -1, 8, 5, shirtColor);
  tile(-3, -5, 6, 5, 0xf4c69c);
  tile(-3, -6, 6, 2, 0x334155);
  tile(-2, -3, 1, 1, 0x0f172a);
  tile(1, -3, 1, 1, 0x0f172a);
  if (state === 'RUNNING') {
    graphics.fillStyle(0x10b981, 1).fillCircle(x + 5 * p, y - 6 * p, 5);
  } else if (state === 'BLOCKED') {
    graphics.fillStyle(0xef4444, 1).fillRect(x + 4 * p, y - 7 * p, 7, 7);
  }
}

export function mountPhaserOffice({ containerEl, listEl, statusEl }) {
  let stopObservingAgents;
  function renderAccessibleList(agents) {
    listEl.replaceChildren();
    agents.forEach((agent) => {
      const li = document.createElement('li');
      const sym = STATE_SYMBOLS[agent.state] || '○';
      const base = `${sym} ${agent.display_name} (${agent.role_id}) · ${agent.state}`;
      li.textContent = agent.active_task_title ? `${base} · ${agent.active_task_title}` : base;
      listEl.append(li);
    });
  }

  function renderMarkers(scene, agents) {
    scene.markers.removeAll(true);
    const figGraphics = scene.add.graphics();
    scene.markers.add(figGraphics);
    const zoneCounts = {};
    agents.forEach((agent) => {
      const zoneKey = ROLE_TO_ZONE[agent.role_id] || 'engineer';
      const zone = ZONE_SLOTS[zoneKey] || ZONE_SLOTS.engineer;
      const idx = zoneCounts[zoneKey] || 0;
      zoneCounts[zoneKey] = idx + 1;
      const x = zone.x - 45 + (idx % 2) * 105;
      const y = zone.y + 8 + Math.floor(idx / 2) * 58;
      const shirt = STATE_COLORS[agent.state] ?? 0x6b7280;
      drawPixelFigure(figGraphics, x, y, shirt, agent.state);
      const sym = STATE_SYMBOLS[agent.state] || '○';
      const label = scene.add
        .text(x, y + 22, `${sym} ${String(agent.display_name).slice(0, 18)}`, {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '12px',
          color: '#edf3f5',
        })
        .setOrigin(0.5, 0);
      scene.markers.add(label);
    });
  }

  async function refresh(scene) {
    try {
      const snapshot = await fetchOfficeSnapshot(4000);
      if (!snapshot.connected || !Array.isArray(snapshot.agent_instances)) {
        throw new Error('Snapshot unavailable');
      }
      stopObservingAgents?.();
      stopObservingAgents = observeOfficeAgents(snapshot, (agents) => {
        renderAccessibleList(agents);
        if (scene) renderMarkers(scene, agents);
        statusEl.textContent = `${agents.length} canlı ajan · Kat 01 DEC-28C (yerel Phaser 3.90.0)`;
      });
    } catch {
      stopObservingAgents?.();
      renderAccessibleList([]);
      if (scene) renderMarkers(scene, []);
      statusEl.textContent = 'Canlı ajan verisine ulaşılamadı.';
    }
  }

  if (!window.Phaser) {
    statusEl.textContent = 'Phaser yüklenemedi. Erişilebilir liste kullanılıyor.';
    void refresh(null);
    return;
  }

  new window.Phaser.Game({
    type: window.Phaser.CANVAS,
    parent: containerEl,
    width: 920,
    height: 490,
    backgroundColor: '#122033',
    banner: false,
    audio: { noAudio: true },
    scene: {
      create() {
        const floor = this.add.graphics();
        // Outer shell + north wall
        floor.fillStyle(0x1b2d44).fillRoundedRect(24, 18, 872, 452, 14);
        floor.fillStyle(0x2c425c).fillRect(24, 18, 872, 20);

        // Main horizontal corridor (F1-COR)
        floor.fillStyle(0x233852).fillRect(40, 212, 840, 48);
        this.add.text(410, 228, 'ANA KORİDOR (F1-COR)', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '11px',
          color: '#94a3b8',
        });

        // 4 active work zones + doorway ticks
        Object.entries(ZONE_SLOTS).forEach(([key, z]) => {
          floor.fillStyle(0x293f59).fillRoundedRect(z.x - 95, z.y - 68, z.w, z.h, 10);
          floor.lineStyle(1.5, z.accent, 0.45).strokeRoundedRect(z.x - 95, z.y - 68, z.w, z.h, 10);
          // Doorway portal on corridor side
          const doorY = key === 'qa' ? z.y - 70 : z.y + 75;
          floor.fillStyle(0x38bdf8, 0.8).fillRect(z.x - 14, doorY, 28, 4);
          this.add.text(z.x - 83, z.y - 58, z.label, {
            fontFamily: 'Segoe UI, system-ui, sans-serif',
            fontSize: '12px',
            color: '#e2e8f0',
          });
        });

        // Passive Reserve (F1-EXP — bottom left, closed door)
        floor.fillStyle(0x18273a).fillRoundedRect(40, 277, 230, 145, 10);
        floor.lineStyle(1, 0x475569, 0.7).strokeRoundedRect(40, 277, 230, 145, 10);
        floor.fillStyle(0xef4444, 0.8).fillRect(140, 275, 28, 4);
        this.add.text(54, 290, 'Pasif Rezerv (F1-EXP)', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '12px',
          color: '#94a3b8',
        });
        this.add.text(54, 314, '2–4 istasyon adayı · Kapalı', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '11px',
          color: '#64748b',
        });

        // Briefing / Entrance (F1-BRIEF — bottom center)
        floor.fillStyle(0x21364f).fillRoundedRect(335, 277, 230, 145, 10);
        floor.lineStyle(1, 0x64748b, 0.6).strokeRoundedRect(335, 277, 230, 145, 10);
        floor.fillStyle(0x38bdf8, 0.8).fillRect(436, 275, 28, 4);
        floor.fillStyle(0x3b5575).fillRoundedRect(395, 336, 110, 36, 16);
        this.add.text(349, 290, 'Briefing / Giriş (F1-BRIEF)', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '12px',
          color: '#cbd5e1',
        });

        // South Entry & Disabled Floor Portal
        this.add.text(412, 444, '↓ ANA GİRİŞ', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '11px',
          color: '#93c5fd',
        });
        this.add.text(685, 444, 'Kat Portali (Kat 02+ · Kapalı)', {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '11px',
          color: '#64748b',
        });

        this.markers = this.add.container(0, 0);
        const poll = async () => {
          await refresh(this);
          if (this.sys.isActive()) this.time.delayedCall(2500, poll);
        };
        void poll();
      },
    },
  });
}
