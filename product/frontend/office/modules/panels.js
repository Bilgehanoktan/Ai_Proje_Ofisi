import { ROLES, ROLE_ID_TO_SCENE_KEY } from './office-canvas.js';

export const AGENT_STATE_LABELS = {
  IDLE: 'Boşta (IDLE)',
  RUNNING: 'Çalışıyor (RUNNING)',
  BLOCKED: 'Engelli (BLOCKED)',
  STALE: 'Güncel değil (STALE)',
};

export function createPanelsController(doc, { onSelectAgent, onMemoryAction, onKaizenAction }) {
  const tabs = [...doc.querySelectorAll('[role="tab"]:not([data-ad-tab])')];
  const adTabs = [...doc.querySelectorAll('[data-ad-tab]')];

  function showAgentDetailTab(panelId, focus = false) {
    adTabs.forEach((tab) => {
      const active = tab.getAttribute('aria-controls') === panelId;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = doc.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
      if (active && focus) tab.focus();
    });
  }

  adTabs.forEach((tab, idx) => {
    tab.addEventListener('click', () => showAgentDetailTab(tab.getAttribute('aria-controls')));
    tab.addEventListener('keydown', (ev) => {
      let next;
      if (ev.key === 'ArrowRight') next = (idx + 1) % adTabs.length;
      if (ev.key === 'ArrowLeft') next = (idx + adTabs.length - 1) % adTabs.length;
      if (ev.key === 'Home') next = 0;
      if (ev.key === 'End') next = adTabs.length - 1;
      if (next !== undefined) {
        ev.preventDefault();
        showAgentDetailTab(adTabs[next].getAttribute('aria-controls'), true);
      }
    });
  });

  function showTab(id, focus = false) {
    tabs.forEach((tab) => {
      const active = tab.getAttribute('aria-controls') === id;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = doc.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
      if (active && focus) tab.focus();
    });
  }

  tabs.forEach((tab, idx) => {
    tab.addEventListener('click', () => showTab(tab.getAttribute('aria-controls')));
    tab.addEventListener('keydown', (ev) => {
      let next;
      if (ev.key === 'ArrowRight') next = (idx + 1) % tabs.length;
      if (ev.key === 'ArrowLeft') next = (idx + tabs.length - 1) % tabs.length;
      if (ev.key === 'Home') next = 0;
      if (ev.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {
        ev.preventDefault();
        showTab(tabs[next].getAttribute('aria-controls'), true);
      }
    });
  });

  function renderLiveList(container, items, emptyText) {
    if (!container) return;
    container.replaceChildren();
    if (!items.length) {
      const p = doc.createElement('p');
      p.textContent = emptyText;
      container.append(p);
      return;
    }
    const ul = doc.createElement('ul');
    ul.className = 'live-list';
    items.forEach(({ title, sub }) => {
      const li = doc.createElement('li');
      const strong = doc.createElement('strong');
      strong.textContent = title;
      const small = doc.createElement('small');
      small.textContent = sub;
      li.append(strong, small);
      ul.append(li);
    });
    container.append(ul);
  }

  function renderAgentContext(agent) {
    if (!agent) return;
    const sceneKey = ROLE_ID_TO_SCENE_KEY[agent.role_id] || 'engineer';
    const role = ROLES[sceneKey] || ROLES.engineer;
    doc.getElementById('context-eyebrow').textContent = 'Canlı AgentInstance kaydı';
    doc.getElementById('role-icon').textContent = role.icon;
    doc.getElementById('role-title').textContent = agent.display_name;
    doc.getElementById('role-sub').textContent = `${agent.role_id} · ${agent.worker_principal}`;
    const cState = doc.getElementById('context-state');
    cState.textContent = AGENT_STATE_LABELS[agent.state] || agent.state;
    cState.classList.toggle('live', agent.state === 'RUNNING' || agent.state === 'IDLE');
    doc.getElementById('role-description').textContent = role.description;
    const taskTitle = agent.state === 'RUNNING' && agent.active_task_id ? agent.active_task_title : '';
    doc.getElementById('context-task-title').textContent = taskTitle || '';
    doc.getElementById('context-task').hidden = !taskTitle;
    const evidence = doc.getElementById('context-evidence');
    evidence.replaceChildren();
    for (const [label, value] of [
      ['Ajan kaydı', agent.agent_instance_id],
      ['Aktif görev', agent.active_task_id],
      ['Aktif deneme', agent.active_attempt_id],
      ['Kayıt sürümü', agent.revision],
      ['Son görülme', agent.last_seen_at],
    ]) {
      const row = doc.createElement('span');
      row.className = 'agent-evidence-row';
      const name = doc.createElement('strong');
      name.textContent = label;
      const detail = doc.createElement('span');
      detail.textContent = value ?? 'Kayıt yok';
      row.append(name, detail);
      evidence.append(row);
    }
    doc.getElementById('context-boundary').textContent =
      'Bilgiler son alınan ajan kaydından gösteriliyor.';
    doc.querySelectorAll('.hotspot').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.role === sceneKey));
    });
  }

  function renderSampleRoleContext(key) {
    const role = ROLES[key];
    if (!role) return;
    doc.getElementById('context-task').hidden = true;
    doc.getElementById('context-eyebrow').textContent = 'Seçili örnek rol';
    const state = doc.getElementById('context-state');
    state.textContent = 'UNVERIFIED';
    state.classList.remove('live');
    doc.getElementById('context-evidence').textContent = 'Bu rol için ajan veya görev kaydı yok.';
    doc.getElementById('context-boundary').textContent = 'Görseldeki rol, ajan etkinliğini temsil etmez.';
    doc.getElementById('role-title').textContent = role.name;
    doc.getElementById('role-sub').textContent = role.sub;
    doc.getElementById('role-description').textContent = role.description;
    doc.getElementById('role-icon').textContent = role.icon;
    doc.querySelectorAll('.hotspot').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.role === key));
    });
    showTab('context');
  }

  function renderAgentInstancesList(instances, selectedId) {
    const list = doc.getElementById('role-list');
    if (!list) return;
    const focusedId = doc.activeElement?.dataset.agentId;
    list.replaceChildren();
    if (!instances.length) {
      doc.getElementById('context-task').hidden = true;
      doc.getElementById('agents-sub').textContent = 'Bu bağlantıda ajan kaydı görünmüyor.';
      doc.getElementById('context-eyebrow').textContent = 'Ajan bağlamı';
      doc.getElementById('role-title').textContent = 'Seçili ajan yok';
      doc.getElementById('role-icon').textContent = '◇';
      const state = doc.getElementById('context-state');
      state.textContent = 'UNVERIFIED';
      state.classList.remove('live');
      for (const id of ['role-sub', 'role-description', 'context-evidence', 'context-boundary']) {
        doc.getElementById(id).textContent = '';
      }
      doc.querySelectorAll('.hotspot').forEach((button) => button.setAttribute('aria-pressed', 'false'));
      return;
    }
    doc.getElementById('agents-sub').textContent =
      `Son ofis verisinde ${instances.length} ajan kaydı var.`;
    instances.forEach((a) => {
      const btn = doc.createElement('button');
      btn.type = 'button';
      btn.dataset.agentId = a.agent_instance_id;
      btn.setAttribute('aria-pressed', String(a.agent_instance_id === selectedId));
      btn.append(doc.createTextNode(`${a.display_name} (${a.role_id})`));
      const small = doc.createElement('small');
      const taskPart = a.state === 'RUNNING' && a.active_task_title ? ` · Görev: ${a.active_task_title}` : '';
      small.textContent = `${AGENT_STATE_LABELS[a.state] || a.state}${taskPart} · id=${a.agent_instance_id.slice(0, 8)}`;
      btn.append(small);
      btn.addEventListener('click', () => onSelectAgent(a.agent_instance_id, true));
      list.append(btn);
      if (focusedId === a.agent_instance_id) btn.focus({ preventScroll: true });
    });
    if (selectedId) {
      const cur = instances.find((a) => a.agent_instance_id === selectedId);
      if (cur) renderAgentContext(cur);
    }
  }

  let lastRuns = [];
  const runsFilterEl = doc.getElementById('office-runs-filter');
  if (runsFilterEl) {
    runsFilterEl.addEventListener('change', () => renderOfficeRuns(lastRuns));
  }

  function renderOfficeRuns(runs) {
    const box = doc.getElementById('office-runs-list');
    if (!box) return;
    lastRuns = Array.isArray(runs) ? runs : [];
    const summaryEl = doc.getElementById('office-runs-summary');
    if (summaryEl) {
      if (!lastRuns.length) {
        summaryEl.textContent = '';
      } else {
        const accepted = lastRuns.filter((r) => r.state === 'ACCEPTED').length;
        const running = lastRuns.filter((r) => r.state === 'RUNNING' || r.state === 'QUEUED').length;
        const failed = lastRuns.filter((r) => r.state === 'REJECTED' || r.state === 'ERROR').length;
        summaryEl.textContent = `Toplam ${lastRuns.length} · Kabul: ${accepted} · Aktif: ${running} · Red/Hata: ${failed}`;
      }
    }
    const activeFilter = runsFilterEl ? runsFilterEl.value : 'ALL';
    const visibleAll = activeFilter === 'ALL'
      ? lastRuns
      : lastRuns.filter((r) => r.state === activeFilter);
    const childrenByParent = new Map();
    lastRuns.forEach((r) => {
      if (r.parent_task_id) {
        const list = childrenByParent.get(r.parent_task_id) || [];
        list.push(r);
        childrenByParent.set(r.parent_task_id, list);
      }
    });
    const visibleIds = new Set(visibleAll.map((r) => r.task_id));
    const rootRuns = visibleAll.filter((r) => !r.parent_task_id || !visibleIds.has(r.parent_task_id));
    const visibleRuns = [...rootRuns].sort((a, b) => {
      const aCeo = a.ceo_final_report?.summary ? 2 : (a.role_id === 'MGR-01' ? 1 : 0);
      const bCeo = b.ceo_final_report?.summary ? 2 : (b.role_id === 'MGR-01' ? 1 : 0);
      return bCeo - aCeo;
    });
    const cards = new Map(Array.from(box.querySelectorAll('.run-card'),
      (card) => [card.dataset.taskId, card]));
    if (!visibleRuns.length) {
      if (box.firstElementChild?.matches('p') && !cards.size) return;
      const empty = doc.createElement('p');
      empty.textContent = lastRuns.length ? 'Seçili filtreye uygun görev yok.' : 'Henüz görev yok.';
      box.replaceChildren(empty);
      return;
    }
    box.querySelector(':scope > p')?.remove();
    const stateLabels = new Map([
      ['QUEUED', 'Kuyrukta'],
      ['RUNNING', 'Çalışıyor'],
      ['ACCEPTED', 'Kabul edildi'],
      ['REJECTED', 'Reddedildi'],
      ['ERROR', 'Hata'],
    ]);
    visibleRuns.forEach((run, index) => {
      let card = cards.get(run.task_id);
      if (!card) {
        card = doc.createElement('article');
        card.className = 'run-card';
        card.dataset.taskId = run.task_id;
        card.innerHTML = '<div class="run-card-head"><h3></h3><span class="run-status"></span></div>'
          + '<p class="run-context"></p><details><summary></summary><div class="run-meta"></div></details>';
        card.querySelector('details').dataset.taskId = run.task_id;
      }
      cards.delete(run.task_id);
      if (box.children[index] !== card) box.insertBefore(card, box.children[index] ?? null);
      card.dataset.state = run.state;
      card.querySelector('h3').textContent = run.title;
      card.querySelector('.run-status').textContent = stateLabels.get(run.state) ?? run.state;
      card.querySelector('.run-context').textContent = `${run.work_type} · ${run.role_id}`;
      const result = card.querySelector('details');
      const meta = result.querySelector('.run-meta');
      const dbNote = run.db_persisted ? 'Kernel PG kaydedildi' : 'Yerel ajan koşusu (Kernel oturumu yok)';
      const verNote = run.verification
        ? `Doğrulama: ${run.verification.reason} (${run.verification.verified_by})`
        : (run.error ? `Hata: ${run.error}` : '');
      const tokNote = run.exec_result
        ? ` · Model: ${run.exec_result.model} · ${run.exec_result.eval_count || 0} token · ${run.exec_result.total_duration_ms || 0} ms`
        : '';
      meta.textContent = [dbNote, verNote].filter(Boolean).join(' · ') + tokNote;
      const response = run.exec_result?.response;
      result.querySelector('summary').textContent = response ? 'Görev çıktısı' : 'Görev ayrıntıları';
      let pre = result.querySelector('.run-output');
      if (response) {
        if (!pre) {
          pre = doc.createElement('pre');
          pre.className = 'run-output';
          result.insertBefore(pre, meta);
        }
        if (pre.textContent !== response) pre.textContent = response;
      } else {
        pre?.remove();
      }

      let receiptEl = result.querySelector('.run-receipt');
      if (run.broker_receipt) {
        if (!receiptEl) {
          receiptEl = doc.createElement('div');
          receiptEl.className = 'run-meta run-receipt';
          result.append(receiptEl);
        }
        const digest = String(run.broker_receipt.source_digest || '').slice(0, 12);
        receiptEl.textContent = `Broker Makbuzu: ${run.broker_receipt.receipt_id || '-'} · digest=${digest || '-'} · doğrulayan=${run.broker_receipt.verified_by || '-'}`;
      } else {
        receiptEl?.remove();
      }

      let treeBox = card.querySelector('.run-tree');
      const children = childrenByParent.get(run.task_id) || [];
      if (children.length) {
        if (!treeBox) {
          treeBox = doc.createElement('div');
          treeBox.className = 'run-tree';
          const treeHead = doc.createElement('div');
          treeHead.className = 'run-tree-head';
          const treeList = doc.createElement('ul');
          treeList.className = 'run-tree-list';
          treeBox.append(treeHead, treeList);
          card.insertBefore(treeBox, result);
        }
        const totalTokens = children.reduce((acc, c) => acc + Number(c.exec_result?.eval_count || 0), 0);
        const totalMs = children.reduce((acc, c) => acc + Number(c.exec_result?.total_duration_ms || 0), 0);
        const acceptedChildren = children.filter((c) => c.state === 'ACCEPTED').length;
        treeBox.querySelector('.run-tree-head').textContent =
          `Delegasyon Ağacı · ${acceptedChildren}/${children.length} alt görev kabul · ${totalTokens} token · ${totalMs} ms`;
        const treeList = treeBox.querySelector('.run-tree-list');
        treeList.replaceChildren();
        children.forEach((child) => {
          const li = doc.createElement('li');
          li.className = 'run-tree-node';
          li.dataset.state = child.state;
          const top = doc.createElement('div');
          top.className = 'run-tree-node-top';
          const nameSpan = doc.createElement('strong');
          nameSpan.textContent = child.title;
          const badgeSpan = doc.createElement('span');
          badgeSpan.className = 'run-status';
          badgeSpan.textContent = stateLabels.get(child.state) ?? child.state;
          top.append(nameSpan, badgeSpan);
          const sub = doc.createElement('small');
          sub.className = 'run-tree-node-meta';
          const cTok = child.exec_result ? `${child.exec_result.eval_count || 0} token · ${child.exec_result.total_duration_ms || 0} ms` : 'bekliyor';
          const cVer = child.verification?.reason || child.error || '';
          sub.textContent = [`${child.work_type} · ${child.role_id}`, cTok, cVer].filter(Boolean).join(' · ');
          li.append(top, sub);
          treeList.append(li);
        });
      } else {
        treeBox?.remove();
      }

      let ceoBox = result.querySelector('.run-ceo-report-box');
      if (run.ceo_final_report?.summary) {
        if (!ceoBox) {
          ceoBox = doc.createElement('div');
          ceoBox.className = 'run-ceo-report-box';
          const head = doc.createElement('div');
          head.className = 'run-ceo-report-head';
          const title = doc.createElement('strong');
          title.textContent = 'CEO Nihai Raporu';
          const copyBtn = doc.createElement('button');
          copyBtn.type = 'button';
          copyBtn.className = 'mini-btn';
          copyBtn.textContent = 'Kopyala';
          copyBtn.addEventListener('click', () => {
            const text = ceoBox.querySelector('.run-ceo-report')?.textContent || '';
            if (navigator?.clipboard?.writeText) {
              navigator.clipboard.writeText(text).then(() => {
                copyBtn.textContent = 'Kopyalandı';
                setTimeout(() => { copyBtn.textContent = 'Kopyala'; }, 1500);
              }).catch(() => {});
            }
          });
          head.append(title, copyBtn);
          const ceoReportEl = doc.createElement('pre');
          ceoReportEl.className = 'run-output run-ceo-report';
          ceoBox.append(head, ceoReportEl);
          result.append(ceoBox);
        }
        const ceoReportEl = ceoBox.querySelector('.run-ceo-report');
        if (ceoReportEl && ceoReportEl.textContent !== run.ceo_final_report.summary) {
          ceoReportEl.textContent = run.ceo_final_report.summary;
        }
      } else {
        ceoBox?.remove();
      }
    });
    for (const removed of cards.values()) removed.remove();
  }

  function renderMemoryPromotions(items, enabled) {
    const box = doc.getElementById('memory-promotions-body');
    if (!box) return;
    box.replaceChildren();
    if (!Array.isArray(items) || !items.length) {
      const p = doc.createElement('p');
      p.textContent = 'Henüz hafıza adayı yok. Kabul edilen görevler otomatik aday üretir.';
      box.append(p);
      return;
    }
    const ul = doc.createElement('ul');
    ul.className = 'live-list';
    items.forEach((m) => {
      const li = doc.createElement('li');
      const strong = doc.createElement('strong');
      strong.textContent = `[${m.state}] ${m.record_id}`;
      const small = doc.createElement('small');
      small.textContent = `${m.summary} · doğrulayan=${m.verified_by || '-'} · terfi=${m.promoted_by || '-'}`;
      li.append(strong, small);
      if (enabled && m.state === 'VERIFIED') {
        const bar = doc.createElement('div');
        bar.className = 'mini-actions';
        const okBtn = doc.createElement('button');
        okBtn.type = 'button';
        okBtn.className = 'mini-btn ok';
        okBtn.textContent = 'Terfi Et (PROMOTED)';
        okBtn.addEventListener('click', () => onMemoryAction(m.record_id, 'promote'));
        const noBtn = doc.createElement('button');
        noBtn.type = 'button';
        noBtn.className = 'mini-btn warn';
        noBtn.textContent = 'Reddet';
        noBtn.addEventListener('click', () => onMemoryAction(m.record_id, 'reject'));
        bar.append(okBtn, noBtn);
        li.append(bar);
      }
      ul.append(li);
    });
    box.append(ul);
  }

  function renderApprovalsBadge(pendingCount) {
    const tab = doc.getElementById('tab-approvals');
    if (!tab) return;
    tab.replaceChildren(doc.createTextNode('Onaylar'));
    if (pendingCount > 0) {
      const badge = doc.createElement('span');
      badge.className = 'tab-badge';
      badge.textContent = String(pendingCount);
      badge.setAttribute('aria-label', `${pendingCount} bekleyen onay`);
      tab.append(' ', badge);
    }
  }

  function renderBudgetAndEffects(budget, effects) {
    const box = doc.getElementById('budget-effects-body');
    if (!box) return;
    box.replaceChildren();
    if (!budget) {
      const p = doc.createElement('p');
      p.textContent = 'Canlı bütçe defteri bağlı değil.';
      box.append(p);
      return;
    }
    const limit = Math.max(0, Number(budget.budget_limit_minor || 0));
    const spent = Math.max(0, Number(budget.spent_minor || 0));
    const held = Math.max(0, Number(budget.held_minor || 0));
    const available = Number(budget.available_minor ?? Math.max(0, limit - spent - held));
    const spentPct = limit > 0 ? Math.min(100, (spent / limit) * 100) : 0;
    const heldPct = limit > 0 ? Math.min(100 - spentPct, (held / limit) * 100) : 0;

    const meter = doc.createElement('div');
    meter.className = 'budget-meter';
    const bar = doc.createElement('div');
    bar.className = 'budget-bar';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', String(limit));
    bar.setAttribute('aria-valuenow', String(spent + held));
    const spentFill = doc.createElement('div');
    spentFill.className = `budget-bar-fill spent${spentPct >= 80 ? ' warn' : ''}`;
    spentFill.style.width = `${spentPct.toFixed(1)}%`;
    const heldFill = doc.createElement('div');
    heldFill.className = 'budget-bar-fill held';
    heldFill.style.width = `${heldPct.toFixed(1)}%`;
    bar.append(spentFill, heldFill);
    meter.append(bar);
    if (budget.blocked_by_unknown) {
      const alert = doc.createElement('p');
      alert.className = 'budget-alert';
      alert.textContent = 'UNKNOWN maliyet kilidi aktif — dış etki uzlaştırması gerekiyor.';
      meter.append(alert);
    }
    box.append(meter);

    const sum = doc.createElement('p');
    sum.textContent = `Limit: ${limit} · Harcanan: ${spent} (${spentPct.toFixed(0)}%) · Blokeli: ${held} · Kalan: ${available}${budget.blocked_by_unknown ? ' · [UNKNOWN KİLİT AKTİF]' : ''}`;
    box.append(sum);
    if (Array.isArray(effects) && effects.length) {
      const listWrap = doc.createElement('div');
      box.append(listWrap);
      renderLiveList(
        listWrap,
        effects.map((e) => ({
          title: `[${e.status}] ${e.provider} (${e.effect_id})`,
          sub: `key=${e.idempotency_key}`,
        })),
        '',
      );
    }
  }

  function renderConnectionLoss(lastSnapshotAt) {
    doc.getElementById('context-task').hidden = true;
    const badge = doc.getElementById('mode-badge');
    badge.classList.remove('live');
    badge.textContent = lastSnapshotAt ? 'Bağlantı kesildi' : 'Canlı veri yok';
    doc.getElementById('stat-freshness').textContent = lastSnapshotAt
      ? `Son okuma ${lastSnapshotAt} · güncel değil`
      : 'Bağlı değil';
    doc.getElementById('office-footer-left').textContent = lastSnapshotAt
      ? 'Son alınan ofis verisi gösteriliyor.'
      : 'Canlı ofis verisi alınamadı.';
    doc.getElementById('office-footer-right').textContent = '';
    doc.getElementById('task-panel-sub').textContent = 'Bağlantı bekleniyor. Görev gönderimi kapalı.';
    doc.getElementById('office-notice').textContent = lastSnapshotAt
      ? 'Ekrandaki son kayıtlar güncel değil.'
      : 'Ofis sunucusundan veri alınamadı.';
    const cState = doc.getElementById('context-state');
    cState.classList.remove('live');
    cState.textContent = 'Bağlantı kesildi · güncel durum doğrulanamıyor';
    doc.getElementById('role-description').textContent =
      'Canlı bağlantı kesildiği için ajanın aktif görev yürütüp yürütmediği doğrulanamıyor.';
    doc.querySelectorAll('#role-list small').forEach((el) => {
      el.textContent = 'Güncel değil · bağlantı bekleniyor';
    });
    const ollama = doc.getElementById('ollama-badge');
    ollama.classList.remove('live');
    ollama.textContent = 'Ollama durumu bilinmiyor';
    doc.getElementById('nav-note').textContent = 'Canlı bağlantı bekleniyor.';
    const fieldset = doc.getElementById('office-task-fieldset');
    if (fieldset) fieldset.disabled = true;
    const evalBtn = doc.getElementById('kaizen-evaluate-btn');
    if (evalBtn) evalBtn.disabled = true;
    const autoBtn = doc.getElementById('kaizen-auto-btn');
    if (autoBtn) autoBtn.disabled = true;
    for (const id of ['nav-kpi-tasks', 'nav-kpi-approvals', 'nav-kpi-budget']) {
      const el = doc.getElementById(id);
      if (el) el.textContent = 'Güncel değil';
    }
  }

  function renderCeoImprovement(snapshot, commandEnabled) {
    const listBox = doc.getElementById('kaizen-proposals-list');
    const healthBadge = doc.getElementById('kaizen-health-badge');
    const subEl = doc.getElementById('kaizen-summary-sub');
    const evalBtn = doc.getElementById('kaizen-evaluate-btn');
    const autoBtn = doc.getElementById('kaizen-auto-btn');
    if (!listBox) return;

    if (evalBtn) evalBtn.disabled = !commandEnabled;
    if (autoBtn) {
      autoBtn.disabled = !commandEnabled;
      const autoOn = Boolean(snapshot?.auto_kaizen_enabled);
      const used = Number(snapshot?.auto_dispatched_count || 0);
      const maxAuto = Number(snapshot?.max_auto_dispatches || 3);
      autoBtn.setAttribute('aria-pressed', String(autoOn));
      autoBtn.classList.toggle('ok', autoOn);
      autoBtn.textContent = autoOn ? `Oto-Kaizen: Açık (${used}/${maxAuto})` : 'Oto-Kaizen: Kapalı';
    }

    if (!snapshot || typeof snapshot !== 'object') {
      if (healthBadge) {
        healthBadge.textContent = 'Sağlık: —';
        healthBadge.classList.remove('live');
      }
      return;
    }

    const m = snapshot.metrics || {};
    const score = Number.isFinite(Number(m.health_score)) ? Number(m.health_score) : 100;
    if (healthBadge) {
      healthBadge.textContent = `Şirket Sağlığı: %${score}`;
      healthBadge.classList.toggle('live', score >= 80);
    }
    if (subEl) {
      const openCount = Number(snapshot.open_proposals_count || 0);
      const dispCount = Number(snapshot.dispatched_proposals_count || 0);
      subEl.textContent =
        `Kabul: ${m.accepted_runs || 0}/${m.total_runs || 0} · Hata/Red: ${m.failed_runs || 0} · `
        + `Bekleyen Terfi: ${m.pending_promotions || 0} · Açık Öneri: ${openCount} · Başlatılan Kaizen: ${dispCount}`;
    }

    const proposals = Array.isArray(snapshot.proposals)
      ? snapshot.proposals.filter((p) => p.state !== 'DISMISSED')
      : [];
    listBox.replaceChildren();
    if (!proposals.length) {
      const p = doc.createElement('p');
      p.textContent = 'Açık iyileştirme önerisi yok. Yeni tarama için "Şirketi Analiz Et" butonunu kullanın.';
      listBox.append(p);
      return;
    }

    const categoryLabels = {
      BUDGET_RECONCILIATION: 'Bütçe & Dış Etki (MOD-014)',
      QUALITY_REMEDIATION: 'Kalite İyileştirme (MOD-003/008)',
      MEMORY_GOVERNANCE: 'Ürün Hafızası Yönetişimi (MOD-012)',
      PROACTIVE_KAIZEN: 'Proaktif Sürekli Gelişim',
    };

    function buildKaizenCard(prop) {
      const card = doc.createElement('article');
      card.className = 'kaizen-card';
      card.dataset.priority = prop.priority || 'NORMAL';
      card.dataset.state = prop.state || 'PROPOSED';

      const top = doc.createElement('div');
      top.className = 'kaizen-card-head';
      const titleEl = doc.createElement('strong');
      titleEl.textContent = prop.title;
      const prioBadge = doc.createElement('span');
      prioBadge.className = `kaizen-prio prio-${String(prop.priority || 'NORMAL').toLowerCase()}`;
      prioBadge.textContent = prop.state === 'DISPATCHED' ? 'GÖREVE DÖNÜŞTÜRÜLDÜ' : (prop.priority || 'NORMAL');
      top.append(titleEl, prioBadge);

      const meta = doc.createElement('small');
      meta.className = 'kaizen-meta';
      const catText = categoryLabels[prop.category] || prop.category;
      meta.textContent = `${catText} · Hedef Rol: ${prop.target_role_id} (${prop.work_type})`;

      const rat = doc.createElement('p');
      rat.className = 'kaizen-rationale';
      rat.textContent = prop.rationale;

      card.append(top, meta, rat);

      if (prop.state === 'PROPOSED' && commandEnabled && onKaizenAction) {
        const actions = doc.createElement('div');
        actions.className = 'mini-actions';
        const runBtn = doc.createElement('button');
        runBtn.type = 'button';
        runBtn.className = 'mini-btn ok kaizen-dispatch-btn';
        runBtn.textContent = 'Görevi Başlat (CEO Delege Etsin)';
        runBtn.addEventListener('click', () => onKaizenAction({ action: 'dispatch', proposal_id: prop.proposal_id }));
        const dismissBtn = doc.createElement('button');
        dismissBtn.type = 'button';
        dismissBtn.className = 'mini-btn kaizen-dismiss-btn';
        dismissBtn.textContent = 'Yoksay';
        dismissBtn.addEventListener('click', () => onKaizenAction({ action: 'dismiss', proposal_id: prop.proposal_id }));
        actions.append(runBtn, dismissBtn);
        card.append(actions);
      } else if (prop.state === 'DISPATCHED' && prop.dispatched_task_id) {
        const linked = doc.createElement('small');
        linked.className = 'kaizen-dispatched-note';
        linked.textContent = `Başlatılan görev: #${String(prop.dispatched_task_id).slice(0, 8)} (Görev sonuçları panelinden izlenebilir)`;
        card.append(linked);
      }
      return card;
    }

    const openProposals = proposals.filter((p) => p.state === 'PROPOSED');
    const dispatchedProposals = proposals.filter((p) => p.state === 'DISPATCHED');

    openProposals.forEach((prop) => {
      listBox.append(buildKaizenCard(prop));
    });

    if (dispatchedProposals.length) {
      const historyEl = doc.createElement('details');
      historyEl.className = 'kaizen-history';
      if (!openProposals.length) historyEl.open = true;
      const summary = doc.createElement('summary');
      summary.textContent = `Başlatılan Kaizen geçmişi (${dispatchedProposals.length})`;
      const historyGrid = doc.createElement('div');
      historyGrid.className = 'kaizen-list kaizen-history-grid';
      dispatchedProposals.forEach((prop) => {
        historyGrid.append(buildKaizenCard(prop));
      });
      historyEl.append(summary, historyGrid);
      listBox.append(historyEl);
    }
  }

  function renderReadinessAndCalibration(readiness, calibrationPayload) {
    const body = doc.getElementById('readiness-calibration-body');
    if (!body) return;
    body.textContent = '';
    const items = [];
    if (readiness) {
      const blockers = Array.isArray(readiness.blockers) ? readiness.blockers : [];
      items.push({
        title: `Uzak dağıtım hazırlığı: ${readiness.ready_for_remote_deploy ? 'HAZIR' : 'ENGELLİ'} (Anahtar: ${readiness.key_status || 'bilinmiyor'})`,
        sub: blockers.length ? `Açık maddeler: ${blockers.join(', ')}` : 'Tüm üretim hazırlık kontrolleri geçti.',
      });
    }
    const cal = calibrationPayload?.calibration;
    if (cal) {
      items.push({
        title: `Doğrulayıcı eşikleri (SOFTWARE ≥ ${(Number(cal.min_software_oracle_pass_ratio) * 100).toFixed(0)}%)`,
        sub: `RESEARCH makbuz ≥ ${cal.min_research_receipt_count} · SPREADSHEET hücre ≥ ${cal.min_spreadsheet_cell_count} · OBLIGATION belirsizlik ≤ ${(Number(cal.max_obligation_uncertainty_ratio) * 100).toFixed(0)}%`,
      });
    }
    renderLiveList(body, items, 'Hazırlık ve kalibrasyon verisi alınamadı.');
  }

  function renderNavKpi({ acceptedTasks, totalTasks, pendingApprovals, availableBudget }) {
    const tEl = doc.getElementById('nav-kpi-tasks');
    const aEl = doc.getElementById('nav-kpi-approvals');
    const bEl = doc.getElementById('nav-kpi-budget');
    if (tEl) {
      tEl.textContent =
        Number.isInteger(totalTasks) && Number.isInteger(acceptedTasks)
          ? `${acceptedTasks} / ${totalTasks}`
          : 'Veri yok';
    }
    if (aEl) {
      aEl.textContent = Number.isInteger(pendingApprovals) ? String(pendingApprovals) : 'Veri yok';
    }
    if (bEl) {
      bEl.textContent = Number.isFinite(availableBudget) ? String(availableBudget) : 'Veri yok';
    }
  }

  function renderSkillLibrary(archPayload) {
    const box = doc.getElementById('skill-library-body');
    if (!box || !archPayload) return;
    box.replaceChildren();

    const fg = archPayload.floor_geometry || {};
    const cat = archPayload.catalog_summary || {};
    const roles = Array.isArray(cat.roles) ? cat.roles : [];
    const skills = Array.isArray(cat.skills) ? cat.skills : [];
    const models = Array.isArray(cat.models) ? cat.models : [];

    const geoP = doc.createElement('p');
    geoP.textContent =
      `Kat Şeması: ${fg.floor_id || '-'} (rev=${fg.layout_revision ?? '-'}, durum=${fg.status || '-'}, `
      + `grid=${fg.grid?.width || 0}×${fg.grid?.height || 0}, bölgeler=${(fg.zones || []).length}, `
      + `digest=${String(fg.geometry_hash || '').slice(0, 23)}…) — Görsel şema yetki üretmez.`;
    box.append(geoP);

    const grid = doc.createElement('div');
    grid.className = 'catalog-grid';

    const makeCol = (headingText, entries) => {
      const col = doc.createElement('div');
      col.className = 'catalog-col';
      const h4 = doc.createElement('h4');
      h4.textContent = headingText;
      col.append(h4);
      renderLiveList(
        col.appendChild(doc.createElement('div')),
        entries,
        'Kayıt yok.',
      );
      return col;
    };

    grid.append(
      makeCol(
        `087 Kanonik Roller (${roles.length})`,
        roles.map((r) => ({
          title: `${r.name} (v${r.version}) · ${r.station_id || '-'}`,
          sub: `Beceriler: ${(r.bound_skills || []).join(', ') || '-'} · ${String(r.digest || '').slice(0, 19)}…`,
        })),
      ),
      makeCol(
        `087 Pinli Beceriler (${skills.length} · Grant Değildir)`,
        skills.map((s) => ({
          title: `${s.name} (v${s.version})`,
          sub: `${s.summary} · ${String(s.digest || '').slice(0, 19)}…`,
        })),
      ),
      makeCol(
        `Yerel Ollama Modelleri (${models.length} · Ücretsiz Varsayılan)`,
        models.map((m) => ({
          title: `${m.name} (v${m.version})`,
          sub: `${m.cost_tier} · ${String(m.digest || '').slice(0, 19)}…`,
        })),
      ),
    );
    box.append(grid);
  }

  function renderAgentDetailView(agent, snapshot, archPayload) {
    const view = doc.getElementById('agent-detail-view');
    if (!view) return;
    const titleEl = doc.getElementById('agent-detail-title');
    const subEl = doc.getElementById('agent-detail-sub');
    const badgeEl = doc.getElementById('agent-detail-badge');

    if (!agent) {
      if (titleEl) titleEl.textContent = 'Canlı Ajan Seçilmedi (Örnek Görünüm)';
      if (subEl) subEl.textContent = 'Yetkili AgentInstance kaydı yok; sahte canlı veri üretilmez.';
      if (badgeEl) {
        badgeEl.textContent = 'UNVERIFIED';
        badgeEl.classList.remove('live');
      }
      for (const pid of ['ad-overview', 'ad-runs', 'ad-skills', 'ad-authority', 'ad-evidence', 'ad-memory', 'ad-audit']) {
        renderLiveList(doc.getElementById(pid), [], 'Seçili canlı AgentInstance kaydı bulunmuyor.');
      }
      return;
    }

    const sceneKey = ROLE_ID_TO_SCENE_KEY[agent.role_id] || 'engineer';
    const roleMeta = ROLES[sceneKey] || ROLES.engineer;
    if (titleEl) titleEl.textContent = `${agent.display_name} (${agent.role_id})`;
    if (subEl) subEl.textContent = `${roleMeta.sub} · worker=${agent.worker_principal}`;
    if (badgeEl) {
      badgeEl.textContent = AGENT_STATE_LABELS[agent.state] || agent.state;
      badgeEl.classList.toggle('live', agent.state === 'RUNNING' || agent.state === 'IDLE');
    }

    const runs = Array.isArray(snapshot?.office_runs)
      ? snapshot.office_runs.filter(
          (r) => r.agent_instance_id === agent.agent_instance_id || r.role_id === agent.role_id,
        )
      : [];
    const cat = archPayload?.catalog_summary || {};
    const roleCard = (cat.roles || []).find((r) => r.name === agent.role_id);
    const boundSkillNames = roleCard?.bound_skills || cat.role_skill_bindings?.[agent.role_id] || [];
    const skillCards = (cat.skills || []).filter((s) => boundSkillNames.includes(s.name));
    const promos = Array.isArray(snapshot?.memory_promotions) ? snapshot.memory_promotions : [];
    const outbox = Array.isArray(snapshot?.outbox) ? snapshot.outbox : [];

    // 1. Overview
    renderLiveList(
      doc.getElementById('ad-overview'),
      [
        { title: 'AgentInstance Kimliği', sub: agent.agent_instance_id || 'Kayıt yok' },
        { title: 'Rol & İstasyon / Bölge', sub: `${agent.role_id} · ${roleCard?.station_id || '-'} · ${roleMeta.zoneId}` },
        { title: 'Durum & Kayıt Sürümü', sub: `${AGENT_STATE_LABELS[agent.state] || agent.state} · rev=${agent.revision ?? '-'}` },
        { title: 'Son Görülme (Heartbeat)', sub: agent.last_seen_at || 'Bilinmiyor' },
      ],
      'Profil kaydı yok.',
    );

    // 2. Runs
    renderLiveList(
      doc.getElementById('ad-runs'),
      runs.map((r) => ({
        title: `[${r.state}] ${r.title}`,
        sub: `${r.work_type} · token=${r.exec_result?.eval_count ?? 0} · süre=${r.exec_result?.total_duration_ms ?? 0} ms`,
      })),
      'Bu ajan/rol için kayıtlı görev koşusu yok.',
    );

    // 3. Skills & 087 Pins
    const skillItems = [];
    if (roleCard) {
      skillItems.push({
        title: `Rol Kartı: ${roleCard.name} (v${roleCard.version})`,
        sub: `${roleCard.digest} · ${roleCard.summary}`,
      });
    }
    skillCards.forEach((sc) => {
      skillItems.push({
        title: `Beceri: ${sc.name} (v${sc.version}) [Grant Değildir]`,
        sub: `${sc.digest} · ${sc.summary}`,
      });
    });
    renderLiveList(
      doc.getElementById('ad-skills'),
      skillItems,
      '087 katalog beceri bağı bulunamadı.',
    );

    // 4. Authority & Lease
    renderLiveList(
      doc.getElementById('ad-authority'),
      [
        { title: 'Kiracı / Proje Kapsamı (088 FORCE RLS)', sub: `tenant=${agent.tenant_id || '-'} · project=${agent.project_id || '-'}` },
        { title: 'Aktif Görev & Deneme (Attempt)', sub: `task=${agent.active_task_id || 'Yok'} · attempt=${agent.active_attempt_id || 'Yok'}` },
        { title: 'Lease Kalan Süre', sub: Number.isFinite(agent.lease_remaining_ms) ? `${agent.lease_remaining_ms} ms` : 'Aktif lease yok' },
        { title: 'Yetki Sınırı (MOD-001)', sub: 'Ofis seçimi veya beceri kartı yetki üretmez; her işlem Kernel yetkisine tabidir.' },
      ],
      'Yetki bilgisi yok.',
    );

    // 5. Evidence & Verification
    const evItems = runs
      .filter((r) => r.verification || r.broker_receipt)
      .map((r) => ({
        title: `${r.title} → ${r.verification?.reason || 'Makbuz kaydı'}`,
        sub: `Doğrulayan: ${r.verification?.verified_by || '-'} · Broker makbuz: ${r.broker_receipt?.receipt_id || 'Yok'}`,
      }));
    renderLiveList(
      doc.getElementById('ad-evidence'),
      evItems,
      'Bu rol için henüz doğrulama veya Broker makbuzu kaydı yok.',
    );

    // 6. Product Memory (MOD-012)
    renderLiveList(
      doc.getElementById('ad-memory'),
      promos.slice(0, 8).map((m) => ({
        title: `[${m.state}] ${m.record_id}`,
        sub: `${m.summary} · doğrulayan=${m.verified_by || '-'} · terfi=${m.promoted_by || '-'}`,
      })),
      'Henüz ürün hafızası adayı yok.',
    );

    // 7. Audit & Event Trail
    const auditItems = [
      ...runs.slice(0, 5).map((r) => ({
        title: `Koşu Durumu: ${r.state} (${r.role_id})`,
        sub: `${r.title} · ${r.updated_at || ''}`,
      })),
      ...outbox.slice(0, 5).map((o) => ({
        title: `Kernel Outbox: ${o.kind}`,
        sub: o.created_at || '',
      })),
    ];
    renderLiveList(
      doc.getElementById('ad-audit'),
      auditItems,
      'Denetim olay izi bulunmuyor.',
    );
  }

  return {
    showTab,
    showAgentDetailTab,
    renderLiveList,
    renderAgentContext,
    renderSampleRoleContext,
    renderAgentInstancesList,
    renderOfficeRuns,
    renderMemoryPromotions,
    renderBudgetAndEffects,
    renderApprovalsBadge,
    renderCeoImprovement,
    renderReadinessAndCalibration,
    renderNavKpi,
    renderSkillLibrary,
    renderAgentDetailView,
    renderConnectionLoss,
  };
}
