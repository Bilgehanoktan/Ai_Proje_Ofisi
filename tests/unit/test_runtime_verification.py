"""Verifier evaluation with explicit launcher/qualification doubles, not OS acceptance."""
import copy
import hashlib
import json
from types import SimpleNamespace
import unittest
from uuid import uuid4

from company_os.verification.runtime_verification import RuntimeTitleVerifier, validate_expected
from company_os.kernel.execution_protocol import Denied, Unknown


def binding():
    return dict(task_id=str(uuid4()),attempt_id=str(uuid4()),patch_id=str(uuid4()),
                fence=1,expected_task_revision=1,head_digest='a'*64,profile_digest='b'*64,
                build_digest='c'*64,acceptance_criteria_digest='d'*64)


class Session:
    def __init__(self):self.response=None;self.closed=0;self.bad=False;self.mutant=False;self.finished=False
    def read_line(self,**kwargs):return b'READY\n' if self.response is None else self.response
    def write_line(self,raw,**kwargs):
        request=json.loads(raw);value=request['value']
        if self.bad:self.response=b'{"checks":[{"result":"PASS"}]}\n';return
        try:
            if self.mutant:result='ok'
            else:
                if not isinstance(value,str):raise TypeError()
                result=' '.join(value.split())
                if not result or len(result)>120:raise ValueError()
            response=dict(id=request['id'],status='SUCCESS',value=result)
        except Exception as exc:response=dict(id=request['id'],status='ERROR',error_type=type(exc).__name__)
        self.response=json.dumps(response).encode()+b'\n'
    def finish(self,**kwargs):
        self.finished=True
        return dict(exit_code=0,stdout_eof=True,stderr_bytes=0,trailing_stdout_bytes=0)
    def close(self):self.closed+=1


class RuntimeVerifierTests(unittest.TestCase):
    def setUp(self):
        self.expected=binding();self.candidate=b'fixture candidate bytes, never executed'
        self.session=Session();self.opens=[];self.phases=[]
        self.resolve=SimpleNamespace(resolve=lambda **kw:dict(expected=kw['expected'],candidate_bytes=self.candidate,
                                       candidate_digest=hashlib.sha256(self.candidate).hexdigest()))
        def open_session(**kwargs):self.opens.append(kwargs);return self.session
        self.launcher=SimpleNamespace(open=open_session)
        def qualify(**kwargs):self.phases.append(kwargs['phase']);return True
        self.qualify=SimpleNamespace(validate=qualify)
        self.subject=RuntimeTitleVerifier(resolver=self.resolve,launcher=self.launcher,qualification=self.qualify)

    def test_evaluator_owns_exact_13_cases_and_checks_qualification_before_after(self):
        result=self.subject.verify(expected=self.expected)
        self.assertEqual((result['passed'],result['total'],result['outcome']),(13,13,'PASS'))
        self.assertEqual(result['expected'],self.expected)
        self.assertEqual(self.phases,['BEFORE_LAUNCH','RUNNING','STOPPED'])
        self.assertTrue(self.session.finished);self.assertEqual(self.session.closed,1)
        self.assertEqual(len(self.opens),1)

    def test_mutant_cannot_supply_pass_total(self):
        self.session.mutant=True
        result=self.subject.verify(expected=self.expected)
        self.assertEqual(result['outcome'],'FAIL');self.assertLess(result['passed'],13)

    def test_candidate_supplied_pass_report_rejected_and_session_closed(self):
        self.session.bad=True
        with self.assertRaises(Denied):self.subject.verify(expected=self.expected)
        self.assertEqual(self.session.closed,1)

    def test_missing_qualification_or_changed_candidate_never_launches(self):
        self.subject.qualification=None
        with self.assertRaises(Denied):self.subject.verify(expected=self.expected)
        self.subject.qualification=self.qualify
        self.resolve.resolve=lambda **kw:dict(expected=kw['expected'],candidate_bytes=b'changed',candidate_digest='0'*64)
        with self.assertRaises(Denied):self.subject.verify(expected=self.expected)
        self.assertEqual(self.opens,[])

    def test_running_or_stop_qualification_rejection_never_issues_receipt(self):
        for phase in ('RUNNING','STOPPED'):
            self.session=Session();seen=[]
            def qualify(**kw):seen.append(kw['phase']);return kw['phase']!=phase
            self.qualify.validate=qualify
            with self.assertRaises(Denied):self.subject.verify(expected=self.expected)
            self.assertIn(phase,seen)
            self.assertEqual(self.session.closed,1)

    def test_cleanup_failure_is_unknown(self):
        self.session.close=lambda: (_ for _ in ()).throw(OSError('fixture close uncertain'))
        with self.assertRaises(Unknown):self.subject.verify(expected=self.expected)

    def test_binding_bool_revisions_or_wrong_fields_rejected(self):
        for changed in [dict(self.expected,fence=True),dict(self.expected,task_id='wrong'),dict(self.expected,verified=True)]:
            with self.assertRaises(Denied):validate_expected(changed)

    def test_nonzero_exit_trailing_output_or_stderr_overflow_never_issues_report(self):
        base=dict(exit_code=0,stdout_eof=True,stderr_bytes=0,trailing_stdout_bytes=0)
        for change in (dict(exit_code=7),dict(exit_code=False),dict(stdout_eof=False),
                       dict(stderr_bytes=16385),dict(trailing_stdout_bytes=1)):
            self.session=Session()
            self.session.finish=lambda **kw:dict(base,**change)
            with self.subTest(change=change),self.assertRaises(Denied):
                self.subject.verify(expected=self.expected)
            self.assertEqual(self.session.closed,1)
