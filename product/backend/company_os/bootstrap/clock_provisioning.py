"""r55/r57/r58 owning-source clock policy, epoch ve sample yazıcısı.

Saat sağlığını stublamaz, SYNC/UNKNOWN veya boot/generation koşullarını
gevşetmez. Yalnız gerçek r58_clock_policy_write, r55_cp_clock_epoch_register
ve r55_cp_clock_sample_persist zincirini exact HMAC kanıtlarıyla çağırır.
"""

import hmac
from uuid import uuid4

from company_os.bootstrap.bootstrap_protocol import context, frame, raw_json
from company_os.bootstrap.provisioning import ProvisioningBlocked

NINE_CLOCK_KEYS = (
    "bounded_handoff_duration_ms",
    "max_uncertainty_ms",
    "max_sample_age_ms",
    "max_clock_jump_ms",
    "first_alert_ms",
    "owner_ack_ms",
    "manual_reconcile_ms",
    "poll_ms",
    "max_drift_ms",
)

DEFAULT_CLOCK_POLICY = {
    "bounded_handoff_duration_ms": 30000,
    "max_uncertainty_ms": 5000,
    "max_sample_age_ms": 60000,
    "max_clock_jump_ms": 5000,
    "first_alert_ms": 15000,
    "owner_ack_ms": 30000,
    "manual_reconcile_ms": 60000,
    "poll_ms": 1000,
    "max_drift_ms": 1000,
}


def validate_clock_policy(policy):
    if type(policy) is not dict or set(policy.keys()) != set(NINE_CLOCK_KEYS):
        raise ProvisioningBlocked("NINE_EXPLICIT_CLOCK_DECISIONS_REQUIRED")
    for k in NINE_CLOCK_KEYS:
        v = policy[k]
        if type(v) is not int or v <= 0:
            raise ProvisioningBlocked("POSITIVE_INTEGER_CLOCK_DECISION_REQUIRED")
    if not (policy["first_alert_ms"] <= policy["owner_ack_ms"] <= policy["manual_reconcile_ms"]):
        raise ProvisioningBlocked("CLOCK_ESCALATION_ORDER")
    return dict(policy)


def clock_policy_tag(key, *, consent_id, issuer_id, key_id, revision, raw):
    if (
        type(key) is not bytes
        or len(key) != 32
        or type(raw) is not bytes
        or not 1 <= len(raw) <= 65536
        or type(revision) is not int
        or revision < 1
    ):
        raise ProvisioningBlocked("INVALID_CLOCK_POLICY_WIRE")
    parts = [
        str(consent_id).encode("utf-8"),
        str(issuer_id).encode("utf-8"),
        str(key_id).encode("utf-8"),
        str(revision).encode("utf-8"),
        raw,
    ]
    return hmac.digest(key, frame(b"R57-CLOCK-POLICY-v1", parts), "sha256")


def clock_observation_tag(secret, *, issuer_id, key_id, revision, raw):
    if (
        type(secret) is not bytes
        or len(secret) != 32
        or type(raw) is not bytes
        or not 1 <= len(raw) <= 65536
        or type(revision) is not int
        or revision < 1
    ):
        raise ProvisioningBlocked("INVALID_CLOCK_PROOF")
    parts = [
        b"CLOCK_OBSERVATION",
        str(issuer_id).encode("utf-8"),
        str(key_id).encode("utf-8"),
        str(revision).encode("utf-8"),
        raw,
    ]
    return hmac.digest(secret, frame(b"R55-CP-PROOF-v1", parts), "sha256")


def activate_clock_policy(
    cursor, record, key, *, consent_id, expected_login, policy, expected_revision=0
):
    if policy is None:
        raise ProvisioningBlocked("EXPLICIT_APPROVED_CLOCK_POLICY_REQUIRED")
    policy = validate_clock_policy(policy)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ProvisioningBlocked("CLOCK_POLICY_STATEMENT_SHAPE")
    statement = {
        "consent_id": str(consent_id),
        "installation_id": str(record["installation_id"]),
        "action": "ACTIVATE",
        "expected_revision": expected_revision,
        "policy": policy,
    }
    ctx = context(cursor, expected_login)
    wire = dict(ctx, statement=statement)
    raw = raw_json(wire)
    tag = clock_policy_tag(
        key,
        consent_id=consent_id,
        issuer_id=record["issuer_id"],
        key_id=record["key_id"],
        revision=record["enrollment_revision"],
        raw=raw,
    )
    cursor.execute(
        "SELECT company_private.r58_clock_policy_write(%s::uuid,%s::bytea,%s::bytea,%s::uuid)",
        (str(consent_id), raw, tag, str(record["key_id"])),
    )
    row = cursor.fetchone()
    if (
        not row
        or type(row[0]) is not dict
        or row[0].get("outcome") not in ("ACTIVATE", "REPLAY_NO_NEW_REVISION")
    ):
        raise ProvisioningBlocked("CLOCK_POLICY_WRITE_FAILED")
    return row[0]


def register_clock_epoch(
    cursor,
    *,
    tenant_id,
    project_id,
    epoch_id,
    issuer_id,
    key_id,
    revision,
    secret,
    host_id,
    host_revision,
    host_generation,
    host_boot_id,
    policy,
    policy_digest,
    current_boottime_ns,
    valid_until_boottime_ns,
    utc_lower_bound,
    utc_upper_bound,
    expected_login="company_clock_runtime_r55",
):
    policy = validate_clock_policy(policy)
    ctx = context(cursor, expected_login)
    stmt = {
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "epoch_id": str(epoch_id),
        "sample_id": str(uuid4()),
        "host_boot_id": str(host_boot_id),
        "host_registration_id": str(host_id),
        "host_registration_revision": int(host_revision),
        "host_generation": int(host_generation),
        "policy_digest": str(policy_digest),
        "backend_pid": ctx["backend_pid"],
        "transaction_id": ctx["transaction_id"],
        "db_login": ctx["db_login"],
        "phase": "FINAL_AFTER_LOCKS",
        "current_boottime_ns": int(current_boottime_ns),
        "valid_until_boottime_ns": int(valid_until_boottime_ns),
        "utc_lower_bound": str(utc_lower_bound),
        "utc_upper_bound": str(utc_upper_bound),
    }
    raw = raw_json(stmt)
    tag = clock_observation_tag(
        secret,
        issuer_id=issuer_id,
        key_id=key_id,
        revision=revision,
        raw=raw,
    )
    cursor.execute(
        "SELECT company_private.r55_cp_clock_epoch_register(%s::uuid,%s::uuid,%s::bigint,%s::bytea,%s::bytea,%s::bytea,%s::uuid,%s::bigint,%s::bigint,%s::jsonb)",
        (
            str(issuer_id),
            str(key_id),
            int(revision),
            raw,
            tag,
            secret,
            str(host_id),
            int(host_revision),
            int(host_generation),
            raw_json(policy).decode("utf-8"),
        ),
    )
    row = cursor.fetchone()
    if not row or str(row[0]) != str(epoch_id):
        raise ProvisioningBlocked("CLOCK_EPOCH_REGISTER_FAILED")
    return str(row[0])


def persist_clock_sample(
    cursor,
    *,
    tenant_id,
    project_id,
    epoch_id,
    sample_id,
    issuer_id,
    key_id,
    revision,
    secret,
    host_id,
    host_revision,
    host_generation,
    host_boot_id,
    source_sequence,
    sample_boottime_ns,
    current_boottime_ns,
    valid_until_boottime_ns,
    sampled_at,
    utc_lower_bound,
    utc_upper_bound,
    sample_uncertainty_ms=5,
    frequency_error_ppm_bound=50,
    sampling_error_margin_ns=100000,
    source_sync_state=None,
    cut_nonce=None,
    expected_login="company_clock_runtime_r55",
):
    if type(source_sequence) is not int or source_sequence < 1:
        raise ProvisioningBlocked("CLOCK_FIRST_SEQUENCE_REQUIRED")
    if source_sync_state is None:
        raise ProvisioningBlocked("EXPLICIT_SOURCE_SYNC_STATE_REQUIRED")
    ctx = context(cursor, expected_login)
    stmt = {
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "epoch_id": str(epoch_id),
        "sample_id": str(sample_id),
        "cut_nonce": str(cut_nonce or uuid4()),
        "host_boot_id": str(host_boot_id),
        "host_registration_id": str(host_id),
        "host_registration_revision": int(host_revision),
        "host_generation": int(host_generation),
        "backend_pid": ctx["backend_pid"],
        "transaction_id": ctx["transaction_id"],
        "db_login": ctx["db_login"],
        "phase": "FINAL_AFTER_LOCKS",
        "source_sequence": int(source_sequence),
        "sampled_at": str(sampled_at),
        "utc_lower_bound": str(utc_lower_bound),
        "utc_upper_bound": str(utc_upper_bound),
        "sample_boottime_ns": int(sample_boottime_ns),
        "current_boottime_ns": int(current_boottime_ns),
        "valid_until_boottime_ns": int(valid_until_boottime_ns),
        "sample_uncertainty_ms": int(sample_uncertainty_ms),
        "frequency_error_ppm_bound": int(frequency_error_ppm_bound),
        "sampling_error_margin_ns": int(sampling_error_margin_ns),
        "source_sync_state": str(source_sync_state),
    }
    raw = raw_json(stmt)
    tag = clock_observation_tag(
        secret,
        issuer_id=issuer_id,
        key_id=key_id,
        revision=revision,
        raw=raw,
    )
    cursor.execute(
        "SELECT company_private.r55_cp_clock_sample_persist(%s::uuid,%s::uuid,%s::bigint,%s::bytea,%s::bytea,%s::bytea)",
        (str(issuer_id), str(key_id), int(revision), raw, tag, secret),
    )
    row = cursor.fetchone()
    if (
        not row
        or type(row[0]) is not dict
        or row[0].get("status") not in ("SAMPLE_PERSISTED_NO_LIVE_CUT", "REPLAY_NO_NEW_CUT")
    ):
        raise ProvisioningBlocked("CLOCK_SAMPLE_PERSIST_FAILED")
    return row[0]
