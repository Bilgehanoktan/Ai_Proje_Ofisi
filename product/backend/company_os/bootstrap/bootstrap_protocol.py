"""r55/r56 exact raw-byte HMAC proof codec; identity/enrollment üretmez."""

import hashlib
import hmac
import json

from company_os.bootstrap.provisioning import ProvisioningBlocked


def raw_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def frame(prefix, parts):
    return prefix + b"\0" + b"".join(str(len(p)).encode("ascii") + b":" + p for p in parts)


def setup_tag(key, *, issuer_id, key_id, revision, raw):
    if (
        type(key) is not bytes
        or len(key) != 32
        or type(raw) is not bytes
        or not 1 <= len(raw) <= 65536
    ):
        raise ProvisioningBlocked("EXACT_ROOT_PROOF_BYTES_REQUIRED")
    if type(revision) is not int or revision < 1:
        raise ProvisioningBlocked("EXACT_KEY_REVISION_REQUIRED")
    parts = [b"SETUP", str(issuer_id).encode(), str(key_id).encode(), str(revision).encode(), raw]
    return hmac.digest(key, frame(b"R55-CP-PROOF-v1", parts), "sha256")


def enter_tag(key, *, installation_id, generation, issuer_id, key_id, revision, raw):
    if (
        type(key) is not bytes
        or len(key) != 32
        or type(raw) is not bytes
        or not 1 <= len(raw) <= 65536
        or type(generation) is not int
        or generation < 1
        or type(revision) is not int
        or revision < 1
    ):
        raise ProvisioningBlocked("EXACT_BOOTSTRAP_PROOF_BYTES_REQUIRED")
    parts = [
        str(installation_id).encode(),
        str(generation).encode(),
        str(issuer_id).encode(),
        str(key_id).encode(),
        str(revision).encode(),
        raw,
    ]
    return hmac.digest(key, frame(b"R56-BOOTSTRAP-v1", parts), "sha256")


def context(cursor, expected_login):
    cursor.execute("SELECT pg_backend_pid(), pg_current_xact_id()::text, session_user")
    row = cursor.fetchone()
    if not row or len(row) != 3 or row[2] != expected_login:
        raise ProvisioningBlocked("EXACT_PROVISIONING_CONTEXT_REQUIRED")
    return {"backend_pid": row[0], "transaction_id": row[1], "db_login": row[2]}


def arm(cursor, record, manifest, key, *, expected_login, utc_lower, utc_upper):
    """Yalnız mevcut enrollment'a karşı arm; yeni trust root oluşturmaz."""
    proof = dict(
        context(cursor, expected_login),
        installation_id=record["installation_id"],
        generation=record["generation"],
        host_boot_id=record["host_boot_id"],
        utc_lower_bound=utc_lower,
        utc_upper_bound=utc_upper,
        manifest=manifest,
    )
    raw = raw_json(proof)
    tag = setup_tag(
        key,
        issuer_id=record["issuer_id"],
        key_id=record["key_id"],
        revision=record["enrollment_revision"],
        raw=raw,
    )
    cursor.execute(
        "SELECT company_private.r55_cp_setup_control_arm(%s::uuid,%s::bigint,%s::bytea,%s::bytea,%s::bytea)",
        (record["installation_id"], record["generation"], raw, tag, key),
    )
    row = cursor.fetchone()
    if not row or str(row[0]) != record["installation_id"]:
        raise ProvisioningBlocked("EXACT_ARM_RESULT_REQUIRED")
    return hashlib.sha256(raw).hexdigest()


def consume(
    cursor,
    record,
    nonce,
    key,
    *,
    expected_login,
    root_proof_digest,
    manifest_digest,
    correlation_id,
):
    if type(nonce) is not bytes or len(nonce) != 32:
        raise ProvisioningBlocked("EXACT_BOOTSTRAP_NONCE_REQUIRED")
    proof = dict(
        context(cursor, expected_login),
        profile="r56.bootstrap-enter.v1",
        phase="BOOTSTRAP_ENTER",
        installation_id=record["installation_id"],
        generation=record["generation"],
        human_id=record["actual_human_id"],
        host_boot_id=record["host_boot_id"],
        nonce_hash=hashlib.sha256(nonce).hexdigest(),
        manifest_digest=manifest_digest,
        root_proof_digest=root_proof_digest,
        release_digest=record["release_digest"],
    )
    raw = raw_json(proof)
    tag = enter_tag(
        key,
        installation_id=record["installation_id"],
        generation=record["generation"],
        issuer_id=record["issuer_id"],
        key_id=record["key_id"],
        revision=record["enrollment_revision"],
        raw=raw,
    )
    cursor.execute(
        "SELECT company_private.r56_bootstrap_consume(%s::uuid,%s::bigint,%s::bytea,%s::bytea,%s::bytea,%s::bytea,%s::uuid)",
        (record["installation_id"], record["generation"], nonce, raw, tag, key, correlation_id),
    )
    row = cursor.fetchone()
    if (
        not row
        or type(row[0]) is not dict
        or row[0].get("state") != "SUCCEEDED"
        or str(row[0].get("result_ref")) != record["installation_id"]
    ):
        raise ProvisioningBlocked("SEALED_BOOTSTRAP_RESULT_REQUIRED")
    return row[0]
