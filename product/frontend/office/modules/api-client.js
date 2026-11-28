export async function fetchOfficeSnapshot(timeoutMs = 5000) {
  const requestedAt = performance.now();
  const response = await fetch('/api/office-live', {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  const snapshot = await response.json();
  snapshot.requestedAt = requestedAt;
  return snapshot;
}

// Deduct the whole request time so network and snapshot collection cannot extend a lease.
export function observeOfficeAgents(snapshot, render) {
  let timer;
  function update() {
    const elapsed = performance.now() - snapshot.requestedAt;
    let nextExpiry = Infinity;
    const records = Array.isArray(snapshot.agent_instances) ? snapshot.agent_instances : [];
    const agents = records.map((agent) => {
      if (agent.state !== 'RUNNING') return agent;
      const remaining = agent.lease_remaining_ms;
      if (agent.active_task_id && agent.active_attempt_id && Number.isFinite(remaining)
          && remaining > elapsed) {
        nextExpiry = Math.min(nextExpiry, remaining - elapsed);
        return agent;
      }
      return { ...agent, state: 'STALE', active_task_title: null, active_task_id: null, active_attempt_id: null };
    });
    render(agents);
    if (Number.isFinite(nextExpiry)) {
      timer = setTimeout(update, Math.min(Math.ceil(nextExpiry), 2147483647));
    }
  }
  update();
  return () => clearTimeout(timer);
}

export async function fetchAgentInstances(tenantId, projectId, timeoutMs = 4000) {
  const qs = new URLSearchParams({ tenant_id: tenantId, project_id: projectId });
  const response = await fetch(`/api/agent-instances?${qs.toString()}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP_${response.status}`);
  }
  return data.agent_instances || [];
}

export async function submitOfficeTask(payload, bearerToken = '') {
  const headers = { 'Content-Type': 'application/json' };
  if (bearerToken) {
    headers.Authorization = `Bearer ${bearerToken}`;
  }
  const response = await fetch('/api/office-tasks', {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    headers,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

export async function sendMemoryAction(recordId, action, actorId = 'OWNER_HUMAN') {
  const response = await fetch('/api/memory-promotions', {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, record_id: recordId, actor_id: actorId }),
  });
  return response.ok;
}

export async function fetchDetailRecord(payload, bearerToken = '') {
  const headers = { 'Content-Type': 'application/json' };
  if (bearerToken) {
    headers.Authorization = `Bearer ${bearerToken}`;
  }
  const response = await fetch('/api/details', {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    headers,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

export async function fetchReadinessSnapshot(timeoutMs = 4000) {
  const response = await fetch('/api/readiness', {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json();
}

export async function fetchVerifierCalibration(timeoutMs = 4000) {
  const response = await fetch('/api/verifier-calibration', {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json();
}

export async function fetchCeoImprovement(timeoutMs = 4000) {
  const response = await fetch('/api/ceo-improvement', {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json();
}

export async function sendCeoImprovementAction(payload, bearerToken = '') {
  const headers = { 'Content-Type': 'application/json' };
  if (bearerToken) {
    headers.Authorization = `Bearer ${bearerToken}`;
  }
  const response = await fetch('/api/ceo-improvement', {
    method: 'POST',
    credentials: 'omit',
    cache: 'no-store',
    headers,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

export async function fetchOfficeArchitecture(tenantId = '', timeoutMs = 4000) {
  const qs = tenantId ? `?${new URLSearchParams({ tenant_id: tenantId }).toString()}` : '';
  const response = await fetch(`/api/office-architecture${qs}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json();
}
