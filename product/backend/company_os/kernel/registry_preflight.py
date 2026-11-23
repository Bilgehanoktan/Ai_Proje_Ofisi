"""Registry readback önkontrolü; kayıt, grant veya policy onayı üretmez."""

REQUIRED = frozenset(
    {
        "CAP-017.revoke",
        "e0.setup_mandate_consume",
        "e0.qualification_candidate_issue",
        "e0.evaluation_artifact_record",
        "qualification.activate",
        "qualification.revoke",
        "objectives.create",
        "plans.create",
        "tasks.create",
    }
)


class RegistryBlocked(ValueError):
    pass


def check_required_registry(rows):
    """Trusted DB adapter readback bekler; başarı authorization kararı değildir.

    Permission anlamını veya policy provenance'ını doğrulamaz. Bu bağımsız
    önkontrol yalnız gerekli başlangıç satırlarının biçim/tutarlılık kapısıdır.
    """
    found = {}
    for row in rows:
        operation = row.get("operation_id")
        if operation not in REQUIRED:
            continue
        if operation in found:
            raise RegistryBlocked("DUPLICATE_OPERATION")
        permission = row.get("permission")
        revision = row.get("policy_revision")
        digest = row.get("approved_policy_digest")
        if not isinstance(permission, str) or not permission.strip():
            raise RegistryBlocked("PERMISSION_REQUIRED")
        if row.get("scope_kind") != "PROJECT":
            raise RegistryBlocked("PROJECT_SCOPE_REQUIRED")
        if row.get("execution_class") not in {"COMMAND", "SPECIAL"}:
            raise RegistryBlocked("COMMAND_CLASS_REQUIRED")
        if type(revision) is not int or revision < 0:
            raise RegistryBlocked("POLICY_REVISION_REQUIRED")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise RegistryBlocked("INVALID_POLICY_DIGEST")
        found[operation] = dict(row)
    missing = REQUIRED - found.keys()
    if missing:
        raise RegistryBlocked("MISSING_OPERATIONS:" + ",".join(sorted(missing)))
    return {
        "shape": "COMPLETE",
        "operations": tuple(sorted(found)),
        "authorization": "NOT_VERIFIED",
    }
