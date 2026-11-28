"""MGR-01 (CEO) Continuous Company Improvement (Kaizen) Engine.

Evaluates live operational telemetry (task runs, rejections/errors, pending MOD-012
memory promotions, and MOD-014 budget/external effect health) to generate bounded,
auditable improvement proposals without creating a second authority outside Kernel.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

KAIZEN_PREFIX = "[CEO-KAIZEN]"
DEFAULT_MAX_AUTO_DISPATCHES = 3

KAIZEN_ROTATION_TRACKS: tuple[dict[str, Any], ...] = (
    {
        "track_id": "sec-rls-audit",
        "title": f"{KAIZEN_PREFIX} Güvenlik ve En Az Yetki Sınır Denetimi",
        "work_type": "RESEARCH",
        "role_id": "MGR-01",
        "rationale": "Periyodik proaktif Kaizen: RLS, en az yetkili servis rolleri ve dış etki sınırlarının gözden geçirilmesi.",
        "goal": (
            "Şirketin güvenlik ve yetki sınırlarını (FORCE RLS, en az yetkili servis rolleri, "
            "loopback/allowlist kontrolleri ve görev ayrılığı) inceleyerek somut sertleştirme "
            "maddeleri ve doğrulama adımları üret."
        ),
        "acceptance_criteria": [
            "En az 3 somut güvenlik/yetki kontrol maddesi ve doğrulama komutu içermeli.",
            "Company Kernel (MOD-001) tek otorite ilkesini korumalı.",
        ],
    },
    {
        "track_id": "qa-verifier-calibration",
        "title": f"{KAIZEN_PREFIX} Kabul Ölçütleri ve Doğrulayıcı Kalibrasyon İncelemesi",
        "work_type": "RESEARCH",
        "role_id": "MGR-01",
        "rationale": "Periyodik proaktif Kaizen: Uzman çıktı kalitesini ve bağımsız doğrulayıcı eşiklerini iyileştirme.",
        "goal": (
            "Dört iş türünde (SOFTWARE, RESEARCH, SPREADSHEET, OBLIGATION) kabul ölçütlerini "
            "ve bağımsız doğrulayıcı kontrollerini inceleyerek yanlış kabul/red risklerini azaltacak "
            "somut kalite standartları öner."
        ),
        "acceptance_criteria": [
            "Her iş türü için ölçülebilir kabul kriteri önerisi içermeli.",
            "Üretici ile doğrulayıcı ayrılığını (producer != verifier) korumalı.",
        ],
    },
    {
        "track_id": "eng-clean-code-kaizen",
        "title": f"{KAIZEN_PREFIX} Kod Kalitesi ve Hata Dayanıklılığı İyileştirmesi",
        "work_type": "SOFTWARE",
        "role_id": "MGR-01",
        "rationale": "Periyodik proaktif Kaizen: Hata yönetimi, atomik yama ve regresyon testi kapsamını güçlendirme.",
        "goal": (
            "Ortak temiz kod kuralları doğrultusunda hata yakalama, kaynak temizliği ve "
            "uçtan uca API/UI bağlantı bütünlüğü için uygulanabilir teknik iyileştirme kontrol listesi hazırla."
        ),
        "acceptance_criteria": [
            "Somut hata senaryoları ve regresyon testi adımları içermeli.",
            "Sessiz hata yutma (silent catch) risklerine karşı önlem belirtmeli.",
        ],
    },
    {
        "track_id": "ops-runbook-readiness",
        "title": f"{KAIZEN_PREFIX} Operasyonel Süreklilik ve Kurtarma Hazırlığı",
        "work_type": "RESEARCH",
        "role_id": "MGR-01",
        "rationale": "Periyodik proaktif Kaizen: Yedekleme, soğuk yeniden başlatma ve üretim hazırlık kontrolleri.",
        "goal": (
            "Yedekten geri yükleme (RTO/RPO), soğuk restart sonrası durum tutarlılığı ve "
            "operasyonel bakım rehberi için güncel hazırlık kontrol raporu oluştur."
        ),
        "acceptance_criteria": [
            "Yedek doğrulama ve restart sonrası okuma kontrollerini içermeli.",
            "Açık ortam kısıtlarını doğrulanmış durumdan net ayırmalı.",
        ],
    },
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CeoImprovementValidationError(ValueError):
    """Raised when a continuous improvement action request is invalid."""


@dataclass
class CeoImprovementProposal:
    proposal_id: str
    dedup_key: str
    category: str
    priority: str
    title: str
    rationale: str
    work_type: str
    target_role_id: str
    task_spec: dict[str, Any]
    state: str = "PROPOSED"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    dispatched_task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "dedup_key": self.dedup_key,
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "rationale": self.rationale,
            "work_type": self.work_type,
            "target_role_id": self.target_role_id,
            "task_spec": dict(self.task_spec),
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "dispatched_task_id": self.dispatched_task_id,
        }


class CeoContinuousImprovementEngine:
    """Bounded continuous improvement loop managed by MGR-01 (CEO) under human governance."""

    def __init__(
        self,
        *,
        task_submitter: Callable[[dict[str, Any], str | None], dict[str, Any]] | None = None,
        max_auto_dispatches: int = DEFAULT_MAX_AUTO_DISPATCHES,
    ) -> None:
        if max_auto_dispatches < 1:
            raise ValueError("max_auto_dispatches must be >= 1")
        self._task_submitter = task_submitter
        self._max_auto_dispatches = max_auto_dispatches
        self._lock = threading.Lock()
        self._proposals: dict[str, CeoImprovementProposal] = {}
        self._proposal_order: list[str] = []
        self._auto_kaizen_enabled = False
        self._auto_dispatched_count = 0
        self._rotation_index = 0
        self._last_evaluated_at: str | None = None
        self._last_metrics: dict[str, Any] = {
            "health_score": 100,
            "total_runs": 0,
            "accepted_runs": 0,
            "failed_runs": 0,
            "active_runs": 0,
            "active_kaizen_runs": 0,
            "pending_promotions": 0,
            "budget_blocked": False,
            "budget_spent_pct": 0.0,
        }

    def bind_task_submitter(
        self, submitter: Callable[[dict[str, Any], str | None], dict[str, Any]]
    ) -> None:
        with self._lock:
            self._task_submitter = submitter

    def evaluate_company_state(
        self,
        *,
        runs: list[dict[str, Any]] | None = None,
        memory_promotions: list[dict[str, Any]] | None = None,
        budget: dict[str, Any] | None = None,
        external_effects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Inspect current company telemetry, refresh proposals, and optionally auto-dispatch 1 bounded task."""
        run_list = list(runs or [])
        promo_list = list(memory_promotions or [])
        effect_list = list(external_effects or [])
        budget_info = dict(budget or {})

        total_runs = len(run_list)
        accepted_runs = sum(1 for r in run_list if r.get("state") == "ACCEPTED")
        failed_runs = sum(1 for r in run_list if r.get("state") in {"REJECTED", "ERROR"})
        active_runs = sum(1 for r in run_list if r.get("state") in {"QUEUED", "RUNNING"})
        active_kaizen_runs = sum(
            1
            for r in run_list
            if r.get("state") in {"QUEUED", "RUNNING"}
            and KAIZEN_PREFIX in str(r.get("title") or "")
        )
        pending_promotions = sum(1 for m in promo_list if m.get("state") == "VERIFIED")
        unknown_effects = sum(1 for e in effect_list if e.get("status") == "UNKNOWN")
        budget_blocked = bool(budget_info.get("blocked_by_unknown")) or unknown_effects > 0

        limit_minor = max(0, int(budget_info.get("budget_limit_minor") or 0))
        spent_minor = max(0, int(budget_info.get("spent_minor") or 0))
        spent_pct = round((spent_minor / limit_minor) * 100.0, 1) if limit_minor > 0 else 0.0

        # Compute transparent operational health score (0..100)
        score = 100
        if total_runs > 0:
            terminal_runs = accepted_runs + failed_runs
            if terminal_runs > 0:
                fail_ratio = failed_runs / terminal_runs
                score -= int(round(fail_ratio * 45))
        if budget_blocked:
            score -= 30
        elif spent_pct >= 80.0:
            score -= 10
        if pending_promotions >= 3:
            score -= 10
        elif pending_promotions >= 1:
            score -= 5
        health_score = max(0, min(100, score))

        candidates: list[tuple[str, str, str, str, str, str, str, dict[str, Any]]] = []

        # 1. Budget & UNKNOWN effect guard (MOD-014)
        if budget_blocked or spent_pct >= 80.0:
            dedup = "budget:unknown-lock" if budget_blocked else "budget:high-utilization"
            prio = "CRITICAL" if budget_blocked else "HIGH"
            title = (
                f"{KAIZEN_PREFIX} UNKNOWN Dış Etki ve Bütçe Kilidi Uzlaştırma Planı"
                if budget_blocked
                else f"{KAIZEN_PREFIX} Bütçe Tüketim Optimizasyonu (%{spent_pct:.0f})"
            )
            rationale = (
                f"MOD-014 bütçe kilidi aktif (UNKNOWN etki={unknown_effects}); yeni dış etkiler durduruldu."
                if budget_blocked
                else f"MOD-014 bütçe kullanımı %{spent_pct:.1f} seviyesine ulaştı (limit={limit_minor})."
            )
            spec = {
                "title": title,
                "work_type": "RESEARCH",
                "role_id": "MGR-01",
                "goal": (
                    f"{rationale} Mevcut dış etki kayıtlarını ve maliyet kalemlerini inceleyerek "
                    "insan sahibine sunulacak somut uzlaştırma ve bütçe koruma adımlarını çıkar."
                ),
                "acceptance_criteria": [
                    "UNKNOWN durumundaki dış etkiler için idempotent uzlaştırma adımlarını listelemeli.",
                    "Otomatik ücretli harcama yasağını ve insan onayı sınırını korumalı.",
                ],
            }
            candidates.append(
                (dedup, "BUDGET_RECONCILIATION", prio, title, rationale, "RESEARCH", "MGR-01", spec)
            )

        # 2. Quality remediation for non-Kaizen failed/rejected runs (MOD-003 / MOD-008)
        non_kaizen_failures = [
            r
            for r in run_list
            if r.get("state") in {"REJECTED", "ERROR"}
            and KAIZEN_PREFIX not in str(r.get("title") or "")
            and "[CEO→REVİZYON]" not in str(r.get("title") or "")
        ]
        seen_failure_roles: set[tuple[str, str]] = set()
        for failed in non_kaizen_failures:
            f_role = str(failed.get("role_id") or "EXP-01")
            f_wtype = str(failed.get("work_type") or "SOFTWARE")
            pair = (f_role, f_wtype)
            if pair in seen_failure_roles:
                continue
            seen_failure_roles.add(pair)
            reason = (
                str((failed.get("verification") or {}).get("reason") or "").strip()
                or str(failed.get("error") or "").strip()
                or "Doğrulama ölçütü karşılanmadı"
            )[:180]
            dedup = f"remediate:{f_role}:{f_wtype}:{reason[:48]}"
            title = f"{KAIZEN_PREFIX} {f_role} ({f_wtype}) Kalite ve Kabul İyileştirmesi"[:180]
            rationale = (
                f"{f_role} rolünde '{failed.get('title', 'görev')}' koşusu {failed.get('state')} aldı "
                f"(Neden: {reason}). Tekrarı önlemek için süreç/kontrol listesi iyileştirmesi öneriliyor."
            )
            spec = {
                "title": title,
                "work_type": "RESEARCH",
                "role_id": "MGR-01",
                "goal": (
                    f"Şirket kalite iyileştirmesi: {f_role} ({f_wtype}) görevinde görülen '{reason}' "
                    "hatasının kök nedenini analiz et; uzman rol ve QA-01 için tekrarlanabilir önleyici "
                    "kabul kontrol listesi oluştur."
                ),
                "acceptance_criteria": [
                    f"'{reason}' kök nedenine yönelik en az 3 önleyici kontrol adımı içermeli.",
                    "Üretici ve bağımsız doğrulayıcı sorumluluklarını ayrı tanımlamalı.",
                ],
            }
            candidates.append(
                (dedup, "QUALITY_REMEDIATION", "HIGH", title, rationale, "RESEARCH", "MGR-01", spec)
            )

        # 3. Pending memory promotion governance (MOD-012 — preserves separation of duties)
        if pending_promotions > 0:
            dedup = "memory:verified-backlog"
            title = f"{KAIZEN_PREFIX} Bekleyen {pending_promotions} Ürün Hafızası Adayı İnceleme Özeti"
            rationale = (
                f"MOD-012 kapsamında {pending_promotions} adet VERIFIED hafıza adayı insan (OWNER_HUMAN) "
                "terfi kararı bekliyor (Görev ayrılığı gereği CEO doğrudan PROMOTED yapamaz)."
            )
            spec = {
                "title": title,
                "work_type": "RESEARCH",
                "role_id": "MGR-01",
                "goal": (
                    f"Bekleyen {pending_promotions} adet VERIFIED ürün hafızası adayının şirket "
                    "standartlarına etkisini değerlendir ve insan sahibinin Onaylar sekmesindeki "
                    "terfi/red kararını hızlandıracak yönetici değerlendirme notunu hazırla."
                ),
                "acceptance_criteria": [
                    "Görev ayrılığı (promoted_by != verified_by) kuralını açıkça korumalı.",
                    "İnsan sahibine net kabul/red değerlendirme ölçütleri sunmalı.",
                ],
            }
            candidates.append(
                (dedup, "MEMORY_GOVERNANCE", "NORMAL", title, rationale, "RESEARCH", "MGR-01", spec)
            )

        unfinished_delegations = sum(
            1
            for r in run_list
            if r.get("delegated_task_ids") and not r.get("ceo_final_report")
        )
        active_task_ids = {
            str(r.get("task_id") or "")
            for r in run_list
            if r.get("state") in {"QUEUED", "RUNNING"}
            or (r.get("delegated_task_ids") and not r.get("ceo_final_report"))
        }

        auto_dispatch_id: str | None = None
        with self._lock:
            self._last_evaluated_at = _now_iso()
            self._last_metrics = {
                "health_score": health_score,
                "total_runs": total_runs,
                "accepted_runs": accepted_runs,
                "failed_runs": failed_runs,
                "active_runs": active_runs,
                "active_kaizen_runs": active_kaizen_runs,
                "pending_promotions": pending_promotions,
                "budget_blocked": budget_blocked,
                "budget_spent_pct": spent_pct,
            }

            open_by_dedup = {
                p.dedup_key: p
                for p in self._proposals.values()
                if p.state == "PROPOSED"
            }
            active_dispatched_dedups = {
                p.dedup_key
                for p in self._proposals.values()
                if p.state in {"DISPATCHING", "DISPATCHED"}
                and (
                    p.category != "MEMORY_GOVERNANCE"
                    or not p.dispatched_task_id
                    or p.dispatched_task_id in active_task_ids
                )
            }

            for dedup, cat, prio, title, rationale, wtype, role_id, spec in candidates:
                if dedup in open_by_dedup:
                    existing_prop = open_by_dedup[dedup]
                    existing_prop.title = title
                    existing_prop.rationale = rationale
                    existing_prop.priority = prio
                    existing_prop.task_spec = spec
                    existing_prop.updated_at = _now_iso()
                    continue
                if dedup in active_dispatched_dedups:
                    continue
                pid = f"kaizen-{uuid4().hex[:10]}"
                prop = CeoImprovementProposal(
                    proposal_id=pid,
                    dedup_key=dedup,
                    category=cat,
                    priority=prio,
                    title=title,
                    rationale=rationale,
                    work_type=wtype,
                    target_role_id=role_id,
                    task_spec=spec,
                )
                self._proposals[pid] = prop
                self._proposal_order.insert(0, pid)
                open_by_dedup[dedup] = prop

            # 4. Always keep at least 1 proactive Kaizen proposal ready when no open proposal exists
            has_open_proposal = any(p.state == "PROPOSED" for p in self._proposals.values())
            if not has_open_proposal:
                for _ in range(len(KAIZEN_ROTATION_TRACKS)):
                    track = KAIZEN_ROTATION_TRACKS[self._rotation_index % len(KAIZEN_ROTATION_TRACKS)]
                    self._rotation_index += 1
                    dedup = f"proactive:{track['track_id']}:{self._rotation_index}"
                    pid = f"kaizen-{uuid4().hex[:10]}"
                    spec = {
                        "title": track["title"],
                        "work_type": track["work_type"],
                        "role_id": track["role_id"],
                        "goal": track["goal"],
                        "acceptance_criteria": list(track["acceptance_criteria"]),
                    }
                    prop = CeoImprovementProposal(
                        proposal_id=pid,
                        dedup_key=dedup,
                        category="PROACTIVE_KAIZEN",
                        priority="NORMAL",
                        title=track["title"],
                        rationale=track["rationale"],
                        work_type=track["work_type"],
                        target_role_id=track["role_id"],
                        task_spec=spec,
                    )
                    self._proposals[pid] = prop
                    self._proposal_order.insert(0, pid)
                    break

            # Bounded auto-kaizen: only when enabled, queue is completely idle, and cap not reached
            if (
                self._auto_kaizen_enabled
                and self._task_submitter is not None
                and active_runs == 0
                and active_kaizen_runs == 0
                and unfinished_delegations == 0
                and self._auto_dispatched_count < self._max_auto_dispatches
            ):
                priority_rank = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2}
                open_props = [p for p in self._proposals.values() if p.state == "PROPOSED"]
                open_props.sort(key=lambda item: priority_rank.get(item.priority, 9))
                if open_props:
                    auto_dispatch_id = open_props[0].proposal_id

        if auto_dispatch_id is not None:
            try:
                self.dispatch_proposal(auto_dispatch_id, counted_as_auto=True)
            except Exception:
                # Never break snapshot/evaluation if task submission fails.
                pass

        return self.snapshot()

    def dispatch_proposal(
        self,
        proposal_id: str,
        *,
        bearer_token: str | None = None,
        counted_as_auto: bool = False,
    ) -> dict[str, Any]:
        clean_id = str(proposal_id or "").strip()
        if not clean_id:
            raise CeoImprovementValidationError("PROPOSAL_ID_REQUIRED")
        with self._lock:
            prop = self._proposals.get(clean_id)
            if prop is None:
                raise KeyError("PROPOSAL_NOT_FOUND")
            if prop.state in {"DISPATCHED", "DISPATCHING"}:
                return prop.to_dict()
            if prop.state != "PROPOSED":
                raise CeoImprovementValidationError(f"PROPOSAL_NOT_DISPATCHABLE:{prop.state}")
            submitter = self._task_submitter
            if submitter is None:
                raise RuntimeError("TASK_SUBMITTER_NOT_CONFIGURED")
            if counted_as_auto and self._auto_dispatched_count >= self._max_auto_dispatches:
                return prop.to_dict()
            prop.state = "DISPATCHING"
            if counted_as_auto:
                self._auto_dispatched_count += 1
            spec_copy = dict(prop.task_spec)

        try:
            created = submitter(spec_copy, bearer_token)
        except Exception:
            with self._lock:
                prop = self._proposals[clean_id]
                prop.state = "PROPOSED"
                if counted_as_auto and self._auto_dispatched_count > 0:
                    self._auto_dispatched_count -= 1
            raise

        task_id = str(created.get("task_id") or "")
        with self._lock:
            prop = self._proposals[clean_id]
            prop.state = "DISPATCHED"
            prop.dispatched_task_id = task_id or None
            prop.updated_at = _now_iso()
            return prop.to_dict()

    def dismiss_proposal(self, proposal_id: str) -> dict[str, Any]:
        clean_id = str(proposal_id or "").strip()
        if not clean_id:
            raise CeoImprovementValidationError("PROPOSAL_ID_REQUIRED")
        with self._lock:
            prop = self._proposals.get(clean_id)
            if prop is None:
                raise KeyError("PROPOSAL_NOT_FOUND")
            if prop.state == "PROPOSED":
                prop.state = "DISMISSED"
                prop.updated_at = _now_iso()
            return prop.to_dict()

    def set_auto_kaizen(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self._auto_kaizen_enabled = bool(enabled)
            if self._auto_kaizen_enabled and self._auto_dispatched_count >= self._max_auto_dispatches:
                # Re-enabling explicitly resets the bounded session counter for a fresh window
                self._auto_dispatched_count = 0
        return self.snapshot()

    def handle_action(
        self,
        payload: dict[str, Any],
        *,
        bearer_token: str | None = None,
        state_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip().lower()
        if action == "evaluate":
            ctx = state_provider() if state_provider is not None else {}
            return self.evaluate_company_state(
                runs=ctx.get("runs"),
                memory_promotions=ctx.get("memory_promotions"),
                budget=ctx.get("budget"),
                external_effects=ctx.get("external_effects"),
            )
        if action == "dispatch":
            proposal = self.dispatch_proposal(
                str(payload.get("proposal_id") or ""),
                bearer_token=bearer_token,
            )
            return {"proposal": proposal, "snapshot": self.snapshot()}
        if action == "dismiss":
            proposal = self.dismiss_proposal(str(payload.get("proposal_id") or ""))
            return {"proposal": proposal, "snapshot": self.snapshot()}
        if action == "set_auto_kaizen":
            if not isinstance(payload.get("enabled"), bool):
                raise CeoImprovementValidationError("BOOLEAN_ENABLED_REQUIRED")
            snap = self.set_auto_kaizen(payload["enabled"])
            if payload["enabled"] and state_provider is not None:
                ctx = state_provider()
                snap = self.evaluate_company_state(
                    runs=ctx.get("runs"),
                    memory_promotions=ctx.get("memory_promotions"),
                    budget=ctx.get("budget"),
                    external_effects=ctx.get("external_effects"),
                )
            return snap
        raise CeoImprovementValidationError(f"UNSUPPORTED_CEO_IMPROVEMENT_ACTION:{action}")

    def snapshot(self, *, limit: int = 12) -> dict[str, Any]:
        with self._lock:
            items = [
                self._proposals[pid].to_dict()
                for pid in self._proposal_order[: max(1, limit)]
                if pid in self._proposals
            ]
            open_count = sum(1 for p in self._proposals.values() if p.state == "PROPOSED")
            dispatched_count = sum(1 for p in self._proposals.values() if p.state == "DISPATCHED")
            return {
                "scope": "LOCAL_OPERATIONAL_TELEMETRY_NOT_KERNEL_AUTHORITY",
                "evaluated_at": self._last_evaluated_at,
                "auto_kaizen_enabled": self._auto_kaizen_enabled,
                "auto_dispatched_count": self._auto_dispatched_count,
                "max_auto_dispatches": self._max_auto_dispatches,
                "open_proposals_count": open_count,
                "dispatched_proposals_count": dispatched_count,
                "metrics": dict(self._last_metrics),
                "proposals": items,
            }
