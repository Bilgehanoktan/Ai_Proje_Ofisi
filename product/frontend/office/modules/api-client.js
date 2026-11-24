export async function fetchOfficeSnapshot(timeoutMs = 5000) {
  const response = await fetch('/api/office-live', {
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
  return response.json();
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
