BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Katalog beklenen erişilebilir fonksiyon imzalarıyla tam karşılaştırılır. Her bilinmeyen SECURITY DEFINER abort üretir.
DO $fence$ DECLARE r record; allowed text[] := ARRAY[
 'company.reject_audit_mutation()',
 'company.install_workflow_plan(jsonb,uuid,text)',
 'company.authorize_effect(uuid,uuid,uuid,uuid)',
 'company.r49_preserve_admission_binding()',
 'company.r49_preserve_tool_request()',
 'company.r49_preserve_workflow_input()',
 'company.r49_outbox_content_immutable()',
 'company.r50_policy_content_immutable()',
 'company.r50_immutable_source()',
 'company.r50_artifact_immutable()',
 'company.r50_report_binding_immutable()',
 'company.r50_command_identity_immutable()',
 'company.r50_stamp_economic_writer()',
 'company.r50_journal_same_transaction()',
 'company.r50_require_balanced_event()',
 'company_private.r51_setup_scope(text,uuid,uuid,uuid)',
 'company.r51_preserve_host_generation()',
 'company.r51f_reservation_identity()',
 'company.r51f_process_identity()',
 'company.r51f_claim_identity()',
 'company.followup_preserve_restore()',
 'company.guard_park_episode_anchor()',
 'company_private.r52_context_enter(text,text,uuid)',
 'company_private.r52_context_exit(uuid)',
 'company_private.r52_scope_allowed(uuid,uuid,text,boolean)',
 'company_private.r53_objectives_create(jsonb)',
 'company_private.r53_revoke_scope(uuid,uuid)',
 'company_private.r53_revoke_project_grant(jsonb)',
 'company_private.r53_grant_chain(uuid,uuid,uuid,text,uuid,uuid)',
 'company_private.r53_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid)',
 'company_private.r53_allowed(uuid,uuid,text,uuid,boolean)',
 'company_private.r53_context_exit(uuid)',
 'company_private.r53_tasks_read(uuid)'
]; BEGIN
 FOR r IN SELECT p.oid::regprocedure::text signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('company','company_private') AND p.prosecdef LOOP
 IF NOT (replace(r.signature,' ','')=ANY(allowed)) THEN RAISE EXCEPTION 'UNKNOWN_DEFINER_ABORT:%',r.signature; END IF; END LOOP; END $fence$;
DO $$ BEGIN IF to_regprocedure('company.reject_audit_mutation()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.reject_audit_mutation() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.install_workflow_plan(jsonb,uuid,text)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.install_workflow_plan(jsonb,uuid,text) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.authorize_effect(uuid,uuid,uuid,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.authorize_effect(uuid,uuid,uuid,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r49_preserve_admission_binding()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r49_preserve_admission_binding() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r49_preserve_tool_request()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r49_preserve_tool_request() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r49_preserve_workflow_input()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r49_preserve_workflow_input() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r49_outbox_content_immutable()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r49_outbox_content_immutable() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_policy_content_immutable()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_policy_content_immutable() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_immutable_source()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_immutable_source() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_artifact_immutable()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_artifact_immutable() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_report_binding_immutable()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_report_binding_immutable() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_command_identity_immutable()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_command_identity_immutable() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_stamp_economic_writer()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_stamp_economic_writer() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_journal_same_transaction()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_journal_same_transaction() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r50_require_balanced_event()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r50_require_balanced_event() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r51_setup_scope(text,uuid,uuid,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r51_setup_scope(text,uuid,uuid,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r51_preserve_host_generation()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r51_preserve_host_generation() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r51f_reservation_identity()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r51f_reservation_identity() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r51f_process_identity()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r51f_process_identity() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.r51f_claim_identity()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.r51f_claim_identity() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.followup_preserve_restore()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.followup_preserve_restore() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company.guard_park_episode_anchor()') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company.guard_park_episode_anchor() FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r52_context_enter(text,text,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r52_context_enter(text,text,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r52_context_exit(uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r52_context_exit(uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r52_scope_allowed(uuid,uuid,text,boolean)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r52_scope_allowed(uuid,uuid,text,boolean) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_objectives_create(jsonb)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_objectives_create(jsonb) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_revoke_scope(uuid,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_revoke_scope(uuid,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_revoke_project_grant(jsonb)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_revoke_project_grant(jsonb) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_grant_chain(uuid,uuid,uuid,text,uuid,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_grant_chain(uuid,uuid,uuid,text,uuid,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_allowed(uuid,uuid,text,uuid,boolean)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_allowed(uuid,uuid,text,uuid,boolean) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_context_exit(uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_context_exit(uuid) FROM PUBLIC'; END IF; END $$;
DO $$ BEGIN IF to_regprocedure('company_private.r53_tasks_read(uuid)') IS NOT NULL THEN EXECUTE 'REVOKE ALL ON FUNCTION company_private.r53_tasks_read(uuid) FROM PUBLIC'; END IF; END $$;
-- Mevcut login/rol üyeliği isimleri tahmin edilmez: canlı katalogdan onaylı allowlist yoksa abort.
-- Canonical trigger owner fonksiyonları DROP edilmez; transport üyelikleri ve eski rollere DML ayrı kesilir.
DO $cut$ DECLARE r record; BEGIN
 FOR r IN SELECT c.oid::regclass::text rel FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('company','company_private') AND c.relkind IN ('r','p') LOOP
 EXECUTE format('REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON TABLE %s FROM PUBLIC',r.rel); END LOOP;
END $cut$;
-- Eski runtime rolleri için exact adlar aşağıdaki kaynak envanterinden alınır; rol yoksa skipped, yeni login üretilmez.
DO $membership$ DECLARE m record; BEGIN FOR m IN SELECT member.rolname AS member_name FROM pg_auth_members am JOIN pg_roles owner_role ON owner_role.oid=am.roleid JOIN pg_roles member ON member.oid=am.member WHERE owner_role.rolname='company_first_run_functions_r53' LOOP EXECUTE format('REVOKE %I FROM %I','company_first_run_functions_r53',m.member_name); END LOOP; END $membership$;
DO $r$ DECLARE f record; BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='company_first_run_functions_r53') THEN FOR f IN SELECT p.oid::regprocedure::text sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('company','company_private') LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.sig,'company_first_run_functions_r53'); END LOOP; EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA company,company_private FROM company_first_run_functions_r53'; END IF; END $r$;
DO $membership$ DECLARE m record; BEGIN FOR m IN SELECT member.rolname AS member_name FROM pg_auth_members am JOIN pg_roles owner_role ON owner_role.oid=am.roleid JOIN pg_roles member ON member.oid=am.member WHERE owner_role.rolname='company_transport_r52' LOOP EXECUTE format('REVOKE %I FROM %I','company_transport_r52',m.member_name); END LOOP; END $membership$;
DO $r$ DECLARE f record; BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='company_transport_r52') THEN FOR f IN SELECT p.oid::regprocedure::text sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('company','company_private') LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.sig,'company_transport_r52'); END LOOP; EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA company,company_private FROM company_transport_r52'; END IF; END $r$;
DO $membership$ DECLARE m record; BEGIN FOR m IN SELECT member.rolname AS member_name FROM pg_auth_members am JOIN pg_roles owner_role ON owner_role.oid=am.roleid JOIN pg_roles member ON member.oid=am.member WHERE owner_role.rolname='company_transport_r53' LOOP EXECUTE format('REVOKE %I FROM %I','company_transport_r53',m.member_name); END LOOP; END $membership$;
DO $r$ DECLARE f record; BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='company_transport_r53') THEN FOR f IN SELECT p.oid::regprocedure::text sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('company','company_private') LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.sig,'company_transport_r53'); END LOOP; EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA company,company_private FROM company_transport_r53'; END IF; END $r$;
ROLLBACK;
