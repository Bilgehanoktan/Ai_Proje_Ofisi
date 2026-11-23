BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
GRANT EXECUTE ON FUNCTION company_private.r53_revoke_project_grant(jsonb) TO company_transport_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_e0_evaluation_artifact_record(uuid,jsonb,text,uuid) TO company_transport_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_e0_setup_mandate_consume(uuid,uuid) TO company_transport_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_qualification_candidate_issue(uuid,timestamptz,text,uuid) TO company_transport_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_qualification_decide(uuid,bigint,uuid,uuid,uuid,boolean,text,uuid) TO company_transport_r54;
ROLLBACK;
