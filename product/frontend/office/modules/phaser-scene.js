import { fetchOfficeSnapshot, observeOfficeAgents } from './api-client.js';

export function mountPhaserFloor({ floor, host, getCharacters }) {
  let scene;

  function refresh() {
    if (!scene) return;
    const bounds = floor.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const scaleX = floor.width / bounds.width;
    const scaleY = floor.height / bounds.height;
    const art = scene.characterArt;
    art.clear();
    for (const { anchor, color } of getCharacters()) {
      const rect = anchor.getBoundingClientRect();
      const x = Math.round((rect.left + rect.width / 2 - bounds.left) * scaleX);
      const y = Math.round((rect.top + rect.height / 2 - bounds.top) * scaleY);
      const size = Math.min(52, rect.height * scaleY);
      const pixel = Math.max(1, Math.floor(size / 12));
      const tile = (dx, dy, w, h, fill) =>
        art.fillStyle(fill).fillRect(x + dx * pixel, y + dy * pixel, w * pixel, h * pixel);
      art.fillStyle(0x080d18, 0.75).fillEllipse(x, y + 6 * pixel, 11 * pixel, 4 * pixel);
      tile(-3, 3, 2, 3, 0x273851);
      tile(1, 3, 2, 3, 0x273851);
      tile(-4, -1, 8, 5, color);
      tile(-3, -5, 6, 5, 0xf4c69c);
      tile(-3, -6, 6, 2, 0x283043);
      tile(-2, -3, 1, 1, 0x283043);
      tile(1, -3, 1, 1, 0x283043);
      tile(-5, 0, 1, 3, 0xf4c69c);
      tile(4, 0, 1, 3, 0xf4c69c);
    }
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

  return { refresh };
}

const STATE_COLORS = {
  IDLE: 0x28665a,
  RUNNING: 0x1d4ed8,
  BLOCKED: 0xad5827,
  STALE: 0x6b7280,
};

const ZONE_SLOTS = {
  'EXP-02': { x: 150, y: 120, label: 'Research' },
  'MGR-01': { x: 450, y: 120, label: 'Orchestrator' },
  'EXP-01': { x: 750, y: 120, label: 'Engineer' },
  'QA-01': { x: 750, y: 310, label: 'QA / Kontrol' },
};

export function mountPhaserOffice({ containerEl, listEl, statusEl }) {
  let stopObservingAgents;
  function renderAccessibleList(agents) {
    listEl.replaceChildren();
    agents.forEach((agent) => {
      const li = document.createElement('li');
      const base = `${agent.display_name} (${agent.role_id}) · ${agent.state}`;
      li.textContent = agent.active_task_title ? `${base} · ${agent.active_task_title}` : base;
      listEl.append(li);
    });
  }

  function renderMarkers(scene, agents) {
    scene.markers.removeAll(true);
    const roleCounts = {};
    agents.forEach((agent) => {
      const zone = ZONE_SLOTS[agent.role_id] || ZONE_SLOTS['EXP-01'];
      const idx = roleCounts[agent.role_id] || 0;
      roleCounts[agent.role_id] = idx + 1;
      const x = zone.x + (idx % 2) * 110;
      const y = zone.y + Math.floor(idx / 2) * 70;
      scene.markers.add(scene.add.ellipse(x, y + 12, 38, 12, 0x18242c));
      scene.markers.add(scene.add.circle(x, y, 14, STATE_COLORS[agent.state] ?? 0x6b7280));
      const label = scene.add
        .text(x, y + 23, String(agent.display_name).slice(0, 20), {
          fontFamily: 'Segoe UI, system-ui, sans-serif',
          fontSize: '13px',
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
        statusEl.textContent = `${agents.length} canlı ajan · Kat 01 (yerel Phaser)`;
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
    width: 900,
    height: 430,
    backgroundColor: '#1d2a34',
    banner: false,
    audio: { noAudio: true },
    scene: {
      create() {
        const floor = this.add.graphics();
        floor.fillStyle(0x304557).fillRoundedRect(40, 30, 820, 370, 12);
        Object.values(ZONE_SLOTS).forEach((z) => {
          floor.fillStyle(0x40596a).fillRoundedRect(z.x - 80, z.y - 50, 220, 140, 8);
          this.add.text(z.x - 70, z.y - 42, z.label, {
            fontFamily: 'Segoe UI, system-ui, sans-serif',
            fontSize: '13px',
            color: '#cbd5e1',
          });
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
