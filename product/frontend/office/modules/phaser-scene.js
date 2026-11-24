import { fetchOfficeSnapshot } from './api-client.js';

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
      const agents = snapshot.agent_instances;
      renderAccessibleList(agents);
      if (scene) renderMarkers(scene, agents);
      statusEl.textContent = `${agents.length} canlı ajan · Kat 01 (yerel Phaser)`;
    } catch {
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
