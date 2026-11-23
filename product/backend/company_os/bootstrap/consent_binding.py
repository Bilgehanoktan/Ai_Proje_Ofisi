"""Yerel kurulum onayı bağlama; bağımsız identity verifier yerine geçmez."""

import copy
import hashlib
import hmac

from company_os.bootstrap.provisioning import ProvisioningBlocked, root_insert


class OwnerConsentBinding:
    """Güvenilir kurulum yapılandırmasındaki exact byte piniyle çalışır.

    Pin ve human_id, kaydın içinden türetilmemeli; trusted supervisor tarafından
    sağlanmalıdır. Bu sınıf enroll_root verifier arayüzünü bilerek sağlamaz.
    """

    def __init__(self, *, consent_sha256, human_id, workspace):
        if (
            type(consent_sha256) is not str
            or len(consent_sha256) != 64
            or any(c not in "0123456789abcdef" for c in consent_sha256)
        ):
            raise ProvisioningBlocked("PINNED_CONSENT_REQUIRED")
        self.digest = consent_sha256
        self.human = human_id
        self.workspace = workspace

    def check(self, raw, consent, record):
        # raw must be the exact bytes parsed below; caller cannot mix documents.
        import json

        if type(raw) is not bytes or len(raw) > 65536:
            raise ProvisioningBlocked("BOUNDED_CONSENT_BYTES_REQUIRED")
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), self.digest):
            raise ProvisioningBlocked("CONSENT_PIN_MISMATCH")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ProvisioningBlocked("DUPLICATE_CONSENT_KEY")
                result[key] = value
            return result

        try:
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        except ValueError, UnicodeError:
            raise ProvisioningBlocked("INVALID_CONSENT_JSON") from None
        if type(parsed) is not dict or parsed != consent:
            raise ProvisioningBlocked("CONSENT_DOCUMENT_MISMATCH")
        if (
            parsed.get("canonical_workspace") != self.workspace
            or parsed.get("installation_consent") != "EXPLICITLY_GRANTED"
            or parsed.get("source") != "DIRECT_USER_STATEMENT_IN_CURRENT_CHAT"
        ):
            raise ProvisioningBlocked("CONSENT_SCOPE_MISMATCH")
        statement = parsed.get("statement")
        if (
            type(statement) is not str
            or parsed.get("statement_sha256")
            != hashlib.sha256(statement.encode("utf-8")).hexdigest()
        ):
            raise ProvisioningBlocked("CONSENT_STATEMENT_MISMATCH")
        root_insert(record)
        if (
            record["actual_human_id"] != self.human
            or record["r56_human_consent_evidence_digest"] != self.digest
        ):
            raise ProvisioningBlocked("ROOT_CONSENT_BINDING_MISMATCH")
        return {
            "record": copy.deepcopy(record),
            "consent_binding": "MATCH",
            "independent_identity": "NOT_VERIFIED",
            "enrollment_authorized": False,
        }


def verify_owner_installation_consent(
    path, *, expected_human_id, expected_document_sha256, expected_workspace, root_record
):
    """Check a trusted external pin/root binding; never grants enrollment authority."""
    import json
    from pathlib import Path
    from types import SimpleNamespace

    with Path(path).open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ProvisioningBlocked("BOUNDED_CONSENT_BYTES_REQUIRED")
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError, UnicodeError:
        raise ProvisioningBlocked("INVALID_CONSENT_JSON") from None
    binding = OwnerConsentBinding(
        consent_sha256=expected_document_sha256,
        human_id=expected_human_id,
        workspace=expected_workspace,
    )
    checked = binding.check(raw, data, root_record)
    return SimpleNamespace(
        matched=(checked["consent_binding"] == "MATCH"),
        authority_granted=False,
        raw=raw,
        parsed=data,
        digest=hashlib.sha256(raw).hexdigest(),
        independent_identity=checked["independent_identity"],
    )
