"""Önceden enrolled root için arm+consume transaction orchestration.

Bu bileşen root enrollment/kimlik/policy onayı yaratmaz. Anahtar sağlayıcısı
trusted supervisor'a aittir; normal model veya UI bu arayüze erişmemelidir.
"""

import hashlib
import json

from company_os.bootstrap.bootstrap_protocol import arm, consume
from company_os.bootstrap.provisioning import (
    ProvisioningBlocked,
    ProvisioningOutcomeUnknown,
    root_insert,
)


def install(
    connect,
    key_provider,
    record,
    manifest,
    nonce,
    *,
    expected_login,
    utc_lower,
    utc_upper,
    correlation_id,
    timeout_ms=2000,
):
    root_insert(record)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
        raise ProvisioningBlocked("BOUNDED_TIMEOUT_REQUIRED")
    if type(nonce) is not bytes or len(nonce) != 32:
        raise ProvisioningBlocked("EXACT_BOOTSTRAP_NONCE_REQUIRED")
    if hashlib.sha256(nonce).hexdigest() != record["r56_approved_nonce_hash"]:
        raise ProvisioningBlocked("APPROVED_NONCE_REQUIRED")
    key = key_provider()
    if (
        type(key) is not bytes
        or len(key) != 32
        or hashlib.sha256(key).hexdigest() != record["key_fingerprint"]
    ):
        raise ProvisioningBlocked("ENROLLED_KEY_REQUIRED")
    payload = json.dumps(manifest, ensure_ascii=False, allow_nan=False)
    connection = connect()
    committing = False
    try:
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise ProvisioningBlocked("IDLE_DEDICATED_TRANSACTION_REQUIRED")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
            for setting in (
                "statement_timeout",
                "lock_timeout",
                "idle_in_transaction_session_timeout",
            ):
                cursor.execute("SELECT set_config(%s,%s,true)", (setting, str(timeout_ms) + "ms"))
            cursor.execute(
                "SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')", (payload,)
            )
            digest = cursor.fetchone()
            if digest != (record["r56_approved_manifest_digest"],):
                raise ProvisioningBlocked("APPROVED_MANIFEST_REQUIRED")
            root_digest = arm(
                cursor,
                record,
                manifest,
                key,
                expected_login=expected_login,
                utc_lower=utc_lower,
                utc_upper=utc_upper,
            )
            result = consume(
                cursor,
                record,
                nonce,
                key,
                expected_login=expected_login,
                root_proof_digest=root_digest,
                manifest_digest=record["r56_approved_manifest_digest"],
                correlation_id=correlation_id,
            )
        committing = True
        connection.commit()
        committing = False
        return result
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        if committing:
            raise ProvisioningOutcomeUnknown("BOOTSTRAP_COMMIT_UNKNOWN_NO_RETRY") from None
        raise ProvisioningBlocked("BOOTSTRAP_NOT_COMMITTED") from None
    finally:
        connection.close()
