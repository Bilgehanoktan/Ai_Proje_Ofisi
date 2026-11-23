BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
ALTER FUNCTION company_private.r63_constructor_result(uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r63_constructor_result(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r63_constructor_result(uuid) TO company_transport_r54;
-- Existing selected constructors, unchanged bodies; explicit host caller closure.
GRANT EXECUTE ON FUNCTION company_private.r53_objectives_create(jsonb),company_private.r54_plans_create(jsonb),company_private.r54_tasks_create(jsonb) TO company_transport_r54;
ROLLBACK;
