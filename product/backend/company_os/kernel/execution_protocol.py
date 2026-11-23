"""Executable r60 protocol guards. No service, migration or process on import.

Authority arguments originate in enrolled Kernel adapters, never model output.
SQLite is solely a local durable intent journal, not the canonical Kernel DB.
"""

import hashlib
import hmac
import json
import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy
from uuid import UUID


class Denied(ValueError):
    pass


class Unknown(RuntimeError):
    pass


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise Denied("EXACT_FIELDS_REQUIRED")


def positive(value):
    if type(value) is not int or value <= 0:
        raise Denied("POSITIVE_INTEGER_REQUIRED")


def uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise Denied("CANONICAL_UUID_REQUIRED")
    return value


def readiness_binding(*, task, plan, head, dependencies):
    if task["state"] != "DRAFT" or task["active_attempt_id"] is not None:
        raise Denied("DRAFT_WITHOUT_ATTEMPT_REQUIRED")
    if task["plan_id"] != plan["id"] or task["project_id"] != plan["project_id"]:
        raise Denied("PLAN_SCOPE")
    if not task["acceptance_criteria"] or not plan["acceptance_criteria"]:
        raise Denied("ACCEPTANCE_CRITERIA_REQUIRED")
    if sorted(task["depends_on"]) != sorted(dependencies) or any(
        d["state"] != "ACCEPTED" for d in dependencies.values()
    ):
        raise Denied("DEPENDENCY_NOT_ACCEPTED")
    return dict(
        task_id=task["id"],
        project_id=task["project_id"],
        task_revision=task["revision"] + 1,
        plan_id=plan["id"],
        plan_revision=plan["revision"],
        head_digest=head,
        role_id=task["role_id"],
        task_criteria_digest=digest(task["acceptance_criteria"]),
        plan_criteria_digest=digest(plan["acceptance_criteria"]),
        dependencies={
            k: dict(revision=v["revision"], state=v["state"])
            for k, v in sorted(dependencies.items())
        },
    )


def ready_claim_current(binding, *, task, plan, head, dependencies):
    t = deepcopy(task)
    t["state"] = "DRAFT"
    t["revision"] -= 1
    if task["state"] != "READY" or task["active_attempt_id"] is not None:
        raise Denied("READY_REQUIRED")
    if readiness_binding(task=t, plan=plan, head=head, dependencies=dependencies) != binding:
        raise Denied("READINESS_BINDING_CHANGED")
    return True


TICKET_FIELDS = {
    "version",
    "delivery_id",
    "issuer_id",
    "key_id",
    "key_revision",
    "audience",
    "expires_boottime_ns",
    "operation",
    "result",
    "command_receipt",
    "snapshot",
}


class TicketCodec:
    def __init__(self, *, key, issuer_id, key_id, key_revision):
        if type(key) is not bytes or len(key) != 32:
            raise Denied("ENROLLED_SECRET_REQUIRED")
        positive(key_revision)
        self.key = key
        self.issuer = uuid(issuer_id)
        self.key_id = uuid(key_id)
        self.revision = key_revision

    def seal_after_commit(self, *, envelope, delivery_id, audience, expires_boottime_ns):
        # This method belongs only to the trusted host, called after execute() returns.
        positive(expires_boottime_ns)
        uuid(delivery_id)
        receipt = envelope["command_receipt"]
        result = envelope["result"]
        if (
            envelope["operation"] != "process.launch_consume"
            or type(receipt) is not dict
            or receipt.get("state") != "SUCCEEDED"
        ):
            raise Denied("COMMITTED_CONSUME_RECEIPT_REQUIRED")
        if (
            result.get("spawn_permitted") is not True
            or result.get("release_only_after_commit") is not True
        ):
            raise Denied("FRESH_PERMISSION_REQUIRED")
        if receipt.get("result_ref") != result.get("capability_id"):
            raise Denied("CAPABILITY_RECEIPT_BINDING")
        ticket = dict(
            version="company.launch-ticket/1",
            delivery_id=delivery_id,
            issuer_id=self.issuer,
            key_id=self.key_id,
            key_revision=self.revision,
            audience=deepcopy(audience),
            expires_boottime_ns=expires_boottime_ns,
            operation=envelope["operation"],
            result=deepcopy(result),
            command_receipt=deepcopy(receipt),
            snapshot=deepcopy(envelope["snapshot"]),
        )
        return dict(
            ticket=ticket,
            tag=hmac.new(
                self.key, b"R60-LAUNCH-DELIVERY\0" + canonical(ticket), "sha256"
            ).hexdigest(),
        )

    def verify(self, wire, *, audience, now):
        exact(wire, {"ticket", "tag"})
        t = wire["ticket"]
        exact(t, TICKET_FIELDS)
        expected = hmac.new(self.key, b"R60-LAUNCH-DELIVERY\0" + canonical(t), "sha256").hexdigest()
        if type(wire["tag"]) is not str or not hmac.compare_digest(wire["tag"], expected):
            raise Denied("TICKET_AUTHENTICITY")
        if (t["version"], t["issuer_id"], t["key_id"], t["key_revision"], t["operation"]) != (
            "company.launch-ticket/1",
            self.issuer,
            self.key_id,
            self.revision,
            "process.launch_consume",
        ):
            raise Denied("TICKET_ENROLLMENT")
        positive(t["expires_boottime_ns"])
        if (
            type(now) is not int
            or now < 0
            or now >= t["expires_boottime_ns"]
            or t["audience"] != audience
        ):
            raise Denied("TICKET_EXPIRED_OR_FOREIGN")
        return deepcopy(t)


class IntentJournal:
    """One-shot intents; parent directory must be private and supervisor-owned.

    SQLite FULL synchronous commit happens before the caller may touch OS state.
    An existing intent is never overwritten or removed by this API.
    """

    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS intents (scope TEXT NOT NULL,identity TEXT NOT NULL,digest TEXT NOT NULL,record TEXT NOT NULL,PRIMARY KEY(scope,identity))"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, scope, identity, record):
        raw = canonical(record).decode()
        d = digest(record)
        try:
            with self.connect() as db:
                db.execute("INSERT INTO intents VALUES(?,?,?,?)", (scope, identity, d, raw))
        except sqlite3.IntegrityError:
            raise Unknown("EXISTING_INTENT_RECONCILE_NO_RETRY") from None
        return d


class CommittedController:
    def __init__(self, *, codec, audience, clock, journal, kernel_guard, controller):
        self.codec = codec
        self.audience = deepcopy(audience)
        self.clock = clock
        self.journal = journal
        self.kernel_guard = kernel_guard
        self.controller = controller

    def dispatch(self, wire):
        t = self.codec.verify(wire, audience=self.audience, now=self.clock())
        # The enrolled guard owns a DB transaction and revoke locks across dispatch.
        with self.kernel_guard(t) as canonical_record:
            expected = dict(
                command_receipt=t["command_receipt"], result=t["result"], snapshot=t["snapshot"]
            )
            if canonical_record != expected:
                raise Denied("CANONICAL_COMMIT_READBACK_REQUIRED")
            self.codec.verify(wire, audience=self.audience, now=self.clock())
            self.journal.reserve(
                "launch-delivery",
                t["result"]["capability_id"],
                dict(delivery_id=t["delivery_id"], ticket_digest=digest(t)),
            )
            try:
                return self.controller.dispatch(t["result"])
            except Exception:
                raise Unknown("DISPATCH_OUTCOME_RECONCILE_NO_RESPAWN") from None


class LeaseWatchdogState:
    """In-process CAS state consumed by the enrolled watchdog loop, not a timer.

    No extension on restart: the launcher must create a fresh object for a new
    process; recovered old intents are reconciled/stopped, never resumed.
    """

    def __init__(self, *, identity, deadline, clock, persist):
        positive(deadline)
        self.identity = deepcopy(identity)
        self.deadline = deadline
        self.clock = clock
        self.persist = persist
        self.revision = 0
        self.pending = None
        self.lock = threading.Lock()

    def prepare(self, proposal):
        with self.lock:
            exact(
                proposal,
                {
                    "extension_id",
                    "identity",
                    "old_deadline",
                    "new_deadline",
                    "revision",
                    "authority_not_after",
                },
            )
            uuid(proposal["extension_id"])
            positive(proposal["new_deadline"])
            positive(proposal["authority_not_after"])
            if (
                proposal["identity"] != self.identity
                or proposal["old_deadline"] != self.deadline
                or proposal["revision"] != self.revision
                or not self.clock()
                < self.deadline
                < proposal["new_deadline"]
                <= proposal["authority_not_after"]
                or self.pending is not None
            ):
                raise Denied("LEASE_PREPARE_CAS")
            self.persist("PREPARED", deepcopy(proposal))
            self.pending = deepcopy(proposal)
            return dict(proposal_digest=digest(proposal), state="PREPARED", extended=False)

    def activate(self, committed_readback):
        with self.lock:
            p = self.pending
            if p is None or committed_readback != dict(
                state="COMMITTED", proposal_digest=digest(p), extension_id=p["extension_id"]
            ):
                raise Denied("COMMITTED_EXTENSION_READBACK_REQUIRED")
            if self.clock() >= self.deadline:
                raise Denied("EXPIRED_LEASE_CANNOT_REVIVE")
            self.persist("ACTIVE", deepcopy(p))
            self.deadline = p["new_deadline"]
            self.revision += 1
            self.pending = None
            return dict(state="ACTIVE", deadline=self.deadline, revision=self.revision)

    def remaining(self):
        with self.lock:
            return max(0, self.deadline - self.clock())


def reconcile_unknown(*, expected, observation, producer_id, controller_id, enrolled_verifier_id):
    exact(
        observation,
        {
            "identity",
            "observer_id",
            "outcome",
            "cgroup_populated",
            "workspace_fenced",
            "no_respawn_intent",
            "usage_zero",
        },
    )
    if observation["observer_id"] != enrolled_verifier_id or enrolled_verifier_id in {
        producer_id,
        controller_id,
    }:
        raise Denied("INDEPENDENT_OBSERVER_REQUIRED")
    if observation["identity"] != expected:
        raise Denied("EXACT_PROCESS_IDENTITY_REQUIRED")
    if observation["outcome"] == "RUNNING":
        return dict(
            state="UNKNOWN_LOCAL",
            stop_required=True,
            respawn_permitted=False,
            release_permitted=False,
        )
    if observation["outcome"] not in {"EXITED", "NOT_STARTED"}:
        raise Denied("DEFINITIVE_OBSERVATION_REQUIRED")
    if (
        type(observation["cgroup_populated"]) is not int
        or observation["cgroup_populated"] != 0
        or observation["workspace_fenced"] is not True
        or observation["no_respawn_intent"] is not True
        or observation["usage_zero"] is not True
    ):
        raise Denied("QUIESCENCE_PROOF_REQUIRED")
    return dict(state="STOPPED_RECONCILED", respawn_permitted=False, release_permitted=True)


def root_replacement(
    *, old_generation, new_generation, human_present, fresh_consent, all_old_attempts_quiescent
):
    if (
        human_present is not True
        or fresh_consent is not True
        or all_old_attempts_quiescent is not True
    ):
        raise Denied("FRESH_HUMAN_CEREMONY_REQUIRED")
    positive(old_generation)
    positive(new_generation)
    if new_generation != old_generation + 1:
        raise Denied("ROOT_GENERATION_CAS")
    return dict(
        new_generation=new_generation, old_generation_revived=False, old_attempt_resume=False
    )


class LeaseRegistry:
    def __init__(self, *, journal, clock):
        self.journal = journal
        self.clock = clock
        self.states = {}
        self.lock = threading.Lock()

    def attach(self, t):
        identity = {
            k: t[k]
            for k in [
                "process_id",
                "attempt_id",
                "fencing_epoch",
                "host_boot_id",
                "controller_generation",
            ]
        }
        with self.lock:
            self.journal.reserve("watchdog-process", t["process_id"], identity)

            def persist(state, proposal):
                self.journal.reserve("watchdog-" + state, proposal["extension_id"], proposal)

            s = LeaseWatchdogState(
                identity=identity,
                deadline=t["not_after_boottime_ns"],
                clock=self.clock,
                persist=persist,
            )
            self.states[t["process_id"]] = s
            return s


class LeaseBridge:
    """Checks both PG_JSONB proposal hash and the local watchdog CAS profile.

    Never compare PG jsonb text hashes with Python canonical JSON hashes. The
    independent Kernel readback binds the former; local state CAS binds the latter.
    """

    def __init__(self, *, watchdog, prepared_signer, active_signer, read_committed):
        self.watchdog = watchdog
        self.prepared_signer = prepared_signer
        self.active_signer = active_signer
        self.read_committed = read_committed
        self.pending = None

    def prepare(self, result):
        raw = result["proposal_raw"]
        p = json.loads(raw)
        if (
            p != result["proposal"]
            or hashlib.sha256(raw.encode()).hexdigest() != result["proposal_digest"]
            or p["extension_id"] != result["extension_id"]
        ):
            raise Denied("KERNEL_PROPOSAL_BYTES_REQUIRED")
        identity = p["identity"]
        expected = self.watchdog.identity
        for key in ["process_id", "attempt_id", "host_boot_id", "controller_generation"]:
            if identity[key] != expected[key]:
                raise Denied("WATCHDOG_PROCESS_IDENTITY")
        if identity["fence"] != expected["fencing_epoch"]:
            raise Denied("WATCHDOG_FENCE")
        local = dict(
            extension_id=p["extension_id"],
            identity=deepcopy(expected),
            old_deadline=p["old_deadline"],
            new_deadline=p["new_deadline"],
            revision=self.watchdog.revision,
            authority_not_after=p["new_deadline"],
        )
        self.watchdog.prepare(local)
        self.pending = (deepcopy(result), local)
        return self.prepared_signer.sign(
            "r60.lease-prepared.v1",
            dict(
                extension_id=p["extension_id"],
                proposal_digest=result["proposal_digest"],
                identity=identity,
                old_deadline=p["old_deadline"],
                new_deadline=p["new_deadline"],
                state="PREPARED",
            ),
        )

    def activate(self):
        if self.pending is None:
            raise Denied("NO_PREPARED_EXTENSION")
        result, local = self.pending
        p = result["proposal"]
        current = self.read_committed(p["extension_id"])
        expected = dict(
            state="COMMITTED",
            extension_id=p["extension_id"],
            proposal_digest=result["proposal_digest"],
            new_deadline=p["new_deadline"],
            identity=p["identity"],
        )
        if current != expected:
            raise Denied("INDEPENDENT_KERNEL_COMMIT_READBACK_REQUIRED")
        activated_at = self.watchdog.clock()
        self.watchdog.activate(
            dict(state="COMMITTED", extension_id=p["extension_id"], proposal_digest=digest(local))
        )
        self.pending = None
        return self.active_signer.sign(
            "r60.lease-active.v1",
            dict(
                extension_id=p["extension_id"],
                proposal_digest=result["proposal_digest"],
                identity=p["identity"],
                active_deadline=p["new_deadline"],
                activated_at_boottime_ns=activated_at,
                state="ACTIVE",
            ),
        )
