\set ON_ERROR_STOP on

\if :{?dc11t4i_apply}
\else
\set dc11t4i_apply 0
\endif

BEGIN;

CREATE TEMP TABLE _dc11t4i_cleanup_params (
    target_wholesaler_id uuid PRIMARY KEY,
    target_code text NOT NULL,
    target_schema text NOT NULL,
    expected_wholesaler_rows integer NOT NULL,
    expected_binding_rows integer NOT NULL,
    expected_retailer_rows integer NOT NULL,
    expected_invitation_rows integer NOT NULL,
    apply_requested boolean NOT NULL
) ON COMMIT DROP;

CREATE TEMP TABLE _dc11t4i_target_retailers (
    retailer_id uuid PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO _dc11t4i_cleanup_params (
    target_wholesaler_id,
    target_code,
    target_schema,
    expected_wholesaler_rows,
    expected_binding_rows,
    expected_retailer_rows,
    expected_invitation_rows,
    apply_requested
)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000'::uuid,
    'TEST001',
    't_550e8400e29b41d4a716446655440000',
    1,
    2,
    2,
    3,
    :dc11t4i_apply::boolean
);

SELECT pg_advisory_xact_lock(hashtext('dc11t4i_test001_cleanup'));

DO $dc11t4i_cleanup$
DECLARE
    target_wholesaler_id uuid;
    target_code text;
    target_schema text;
    expected_wholesaler_rows integer;
    expected_binding_rows integer;
    expected_retailer_rows integer;
    expected_invitation_rows integer;
    apply_requested boolean;
    wholesaler_rows integer;
    code_rows integer;
    registration_rows integer;
    platform_tenant_rows integer;
    audit_rows integer;
    reset_token_rows integer;
    unknown_fk_rows integer;
    binding_rows integer;
    retailer_rows integer;
    invitation_rows integer;
    shared_retailer_rows integer;
    non_target_invitation_rows integer;
    schema_rows integer;
    deleted_invitation_rows integer := 0;
    deleted_retailer_rows integer := 0;
    deleted_wholesaler_rows integer := 0;
    residual_rows integer;
BEGIN
    SELECT
        params.target_wholesaler_id,
        params.target_code,
        params.target_schema,
        params.expected_wholesaler_rows,
        params.expected_binding_rows,
        params.expected_retailer_rows,
        params.expected_invitation_rows,
        params.apply_requested
    INTO
        target_wholesaler_id,
        target_code,
        target_schema,
        expected_wholesaler_rows,
        expected_binding_rows,
        expected_retailer_rows,
        expected_invitation_rows,
        apply_requested
    FROM _dc11t4i_cleanup_params AS params;

    IF target_wholesaler_id <> '550e8400-e29b-41d4-a716-446655440000'::uuid THEN
        RAISE EXCEPTION 'STOP anchor wholesaler mismatch';
    END IF;

    IF target_code <> 'TEST001' THEN
        RAISE EXCEPTION 'STOP anchor code mismatch';
    END IF;

    IF target_schema <> 't_550e8400e29b41d4a716446655440000' THEN
        RAISE EXCEPTION 'STOP anchor schema mismatch';
    END IF;

    IF target_schema !~ '^t_[0-9a-f]{32}$'
        OR target_schema <> 't_' || replace(target_wholesaler_id::text, '-', '') THEN
        RAISE EXCEPTION 'STOP invalid tenant schema anchor';
    END IF;

    SELECT count(*) INTO unknown_fk_rows
    FROM (
        SELECT
            source_namespace.nspname || '.' || source_table.relname AS source_table,
            con.conname AS constraint_name,
            target_namespace.nspname || '.' || target_table.relname AS target_table
        FROM pg_constraint AS con
        JOIN pg_class AS source_table
          ON source_table.oid = con.conrelid
        JOIN pg_namespace AS source_namespace
          ON source_namespace.oid = source_table.relnamespace
        JOIN pg_class AS target_table
          ON target_table.oid = con.confrelid
        JOIN pg_namespace AS target_namespace
          ON target_namespace.oid = target_table.relnamespace
        WHERE con.contype = 'f'
          AND con.confrelid IN (
              'public.wholesalers'::regclass,
              'public.retailers'::regclass,
              'public.tenant_registrations'::regclass
          )
    ) AS found
    LEFT JOIN (
        VALUES
            ('public.email_verification_tokens', 'email_verification_tokens_registration_id_fkey', 'public.tenant_registrations'),
            ('public.invitations', 'invitations_wholesaler_id_fkey', 'public.wholesalers'),
            ('public.invitations', 'invitations_used_retailer_id_fkey', 'public.retailers'),
            ('public.onboarding_status_tokens', 'onboarding_status_tokens_registration_id_fkey', 'public.tenant_registrations'),
            ('public.owner_credential_setup_tokens', 'owner_credential_setup_tokens_registration_id_fkey', 'public.tenant_registrations'),
            ('public.password_reset_tokens', 'password_reset_tokens_tenant_id_fkey', 'public.wholesalers'),
            ('public.platform_audit_logs', 'platform_audit_logs_wholesaler_id_fkey', 'public.wholesalers'),
            ('public.platform_tenants', 'platform_tenants_wholesaler_id_fkey', 'public.wholesalers'),
            ('public.tenant_registrations', 'tenant_registrations_wholesaler_id_fkey', 'public.wholesalers'),
            ('public.wholesaler_retailer_bindings', 'wholesaler_retailer_bindings_retailer_id_fkey', 'public.retailers'),
            ('public.wholesaler_retailer_bindings', 'wholesaler_retailer_bindings_wholesaler_id_fkey', 'public.wholesalers')
    ) AS expected(source_table, constraint_name, target_table)
      ON expected.source_table = found.source_table
     AND expected.constraint_name = found.constraint_name
     AND expected.target_table = found.target_table
    WHERE expected.constraint_name IS NULL;

    IF unknown_fk_rows <> 0 THEN
        RAISE EXCEPTION 'STOP unknown FK dependency count %', unknown_fk_rows;
    END IF;

    SELECT count(*) INTO wholesaler_rows
    FROM public.wholesalers
    WHERE id = target_wholesaler_id
      AND code = target_code;

    SELECT count(*) INTO code_rows
    FROM public.wholesalers
    WHERE code = target_code;

    IF wholesaler_rows = 0 THEN
        SELECT count(*) INTO residual_rows
        FROM public.wholesalers
        WHERE id = target_wholesaler_id
           OR code = target_code;

        IF residual_rows <> 0 THEN
            RAISE EXCEPTION 'STOP partial TEST001 wholesaler identity residual %', residual_rows;
        END IF;

        SELECT count(*) INTO residual_rows
        FROM public.wholesaler_retailer_bindings
        WHERE wholesaler_id = target_wholesaler_id;

        SELECT residual_rows + count(*) INTO residual_rows
        FROM public.invitations
        WHERE wholesaler_id = target_wholesaler_id;

        SELECT residual_rows + count(*) INTO residual_rows
        FROM public.tenant_registrations
        WHERE wholesaler_id = target_wholesaler_id
           OR tenant_code = target_code
           OR tenant_schema = target_schema;

        SELECT residual_rows + count(*) INTO residual_rows
        FROM public.password_reset_tokens
        WHERE tenant_id = target_wholesaler_id
           OR tenant_schema = target_schema;

        SELECT residual_rows + count(*) INTO residual_rows
        FROM public.platform_tenants
        WHERE wholesaler_id = target_wholesaler_id;

        SELECT residual_rows + count(*) INTO residual_rows
        FROM public.platform_audit_logs
        WHERE wholesaler_id = target_wholesaler_id
           OR resource LIKE '%' || target_wholesaler_id::text || '%'
           OR resource LIKE '%' || target_code || '%'
           OR resource LIKE '%' || target_schema || '%'
           OR audit_metadata::text LIKE '%' || target_wholesaler_id::text || '%'
           OR audit_metadata::text LIKE '%' || target_code || '%'
           OR audit_metadata::text LIKE '%' || target_schema || '%';

        SELECT residual_rows + count(*) INTO residual_rows
        FROM information_schema.schemata
        WHERE schema_name = target_schema;

        IF residual_rows <> 0 THEN
            RAISE EXCEPTION 'STOP partial TEST001 cleanup residual count %', residual_rows;
        END IF;

        RAISE NOTICE 'DC11T4I_TEST001_CLEANUP_MODE=IDEMPOTENT_NOOP';
        RETURN;
    END IF;

    IF wholesaler_rows <> expected_wholesaler_rows OR code_rows <> expected_wholesaler_rows THEN
        RAISE EXCEPTION 'STOP TEST001 wholesaler count mismatch';
    END IF;

    SELECT count(*) INTO registration_rows
    FROM public.tenant_registrations
    WHERE wholesaler_id = target_wholesaler_id
       OR tenant_code = target_code
       OR tenant_schema = target_schema;

    IF registration_rows <> 0 THEN
        RAISE EXCEPTION 'STOP unexpected tenant registration count %', registration_rows;
    END IF;

    SELECT count(*) INTO platform_tenant_rows
    FROM public.platform_tenants
    WHERE wholesaler_id = target_wholesaler_id;

    IF platform_tenant_rows <> 0 THEN
        RAISE EXCEPTION 'STOP unexpected platform tenant count %', platform_tenant_rows;
    END IF;

    SELECT count(*) INTO audit_rows
    FROM public.platform_audit_logs
    WHERE wholesaler_id = target_wholesaler_id
       OR resource LIKE '%' || target_wholesaler_id::text || '%'
       OR resource LIKE '%' || target_code || '%'
       OR resource LIKE '%' || target_schema || '%'
       OR audit_metadata::text LIKE '%' || target_wholesaler_id::text || '%'
       OR audit_metadata::text LIKE '%' || target_code || '%'
       OR audit_metadata::text LIKE '%' || target_schema || '%';

    IF audit_rows <> 0 THEN
        RAISE EXCEPTION 'STOP unexpected platform audit evidence count %', audit_rows;
    END IF;

    SELECT count(*) INTO reset_token_rows
    FROM public.password_reset_tokens
    WHERE tenant_id = target_wholesaler_id
       OR tenant_schema = target_schema;

    IF reset_token_rows <> 0 THEN
        RAISE EXCEPTION 'STOP unexpected reset-token evidence count %', reset_token_rows;
    END IF;

    INSERT INTO _dc11t4i_target_retailers (retailer_id)
    SELECT DISTINCT retailer_id
    FROM public.wholesaler_retailer_bindings
    WHERE wholesaler_id = target_wholesaler_id;

    SELECT count(*) INTO binding_rows
    FROM public.wholesaler_retailer_bindings
    WHERE wholesaler_id = target_wholesaler_id;

    SELECT count(*) INTO retailer_rows
    FROM _dc11t4i_target_retailers;

    SELECT count(*) INTO invitation_rows
    FROM public.invitations
    WHERE wholesaler_id = target_wholesaler_id;

    SELECT count(*) INTO schema_rows
    FROM information_schema.schemata
    WHERE schema_name = target_schema;

    IF binding_rows <> expected_binding_rows THEN
        RAISE EXCEPTION 'STOP TEST001 binding count mismatch %', binding_rows;
    END IF;

    IF retailer_rows <> expected_retailer_rows THEN
        RAISE EXCEPTION 'STOP TEST001 retailer count mismatch %', retailer_rows;
    END IF;

    IF invitation_rows <> expected_invitation_rows THEN
        RAISE EXCEPTION 'STOP TEST001 invitation count mismatch %', invitation_rows;
    END IF;

    IF schema_rows <> 1 THEN
        RAISE EXCEPTION 'STOP TEST001 schema count mismatch %', schema_rows;
    END IF;

    SELECT count(*) INTO shared_retailer_rows
    FROM _dc11t4i_target_retailers AS target_retailers
    JOIN public.wholesaler_retailer_bindings AS bindings
      ON bindings.retailer_id = target_retailers.retailer_id
    WHERE bindings.wholesaler_id <> target_wholesaler_id;

    IF shared_retailer_rows <> 0 THEN
        RAISE EXCEPTION 'STOP shared retailer dependency count %', shared_retailer_rows;
    END IF;

    SELECT count(*) INTO non_target_invitation_rows
    FROM public.invitations AS invitations
    JOIN _dc11t4i_target_retailers AS target_retailers
      ON target_retailers.retailer_id = invitations.used_retailer_id
    WHERE invitations.wholesaler_id <> target_wholesaler_id;

    IF non_target_invitation_rows <> 0 THEN
        RAISE EXCEPTION 'STOP non-target invitation dependency count %', non_target_invitation_rows;
    END IF;

    DELETE FROM public.invitations
    WHERE wholesaler_id = target_wholesaler_id;
    GET DIAGNOSTICS deleted_invitation_rows = ROW_COUNT;

    IF deleted_invitation_rows <> expected_invitation_rows THEN
        RAISE EXCEPTION 'STOP invitation delete count mismatch %', deleted_invitation_rows;
    END IF;

    EXECUTE format('DROP SCHEMA %I CASCADE', target_schema);

    DELETE FROM public.retailers
    WHERE id IN (SELECT retailer_id FROM _dc11t4i_target_retailers);
    GET DIAGNOSTICS deleted_retailer_rows = ROW_COUNT;

    IF deleted_retailer_rows <> expected_retailer_rows THEN
        RAISE EXCEPTION 'STOP retailer delete count mismatch %', deleted_retailer_rows;
    END IF;

    DELETE FROM public.wholesalers
    WHERE id = target_wholesaler_id
      AND code = target_code;
    GET DIAGNOSTICS deleted_wholesaler_rows = ROW_COUNT;

    IF deleted_wholesaler_rows <> expected_wholesaler_rows THEN
        RAISE EXCEPTION 'STOP wholesaler delete count mismatch %', deleted_wholesaler_rows;
    END IF;

    SELECT count(*) INTO residual_rows
    FROM public.wholesalers
    WHERE id = target_wholesaler_id
       OR code = target_code;

    SELECT residual_rows + count(*) INTO residual_rows
    FROM public.wholesaler_retailer_bindings
    WHERE wholesaler_id = target_wholesaler_id
       OR retailer_id IN (SELECT retailer_id FROM _dc11t4i_target_retailers);

    SELECT residual_rows + count(*) INTO residual_rows
    FROM public.retailers
    WHERE id IN (SELECT retailer_id FROM _dc11t4i_target_retailers);

    SELECT residual_rows + count(*) INTO residual_rows
    FROM public.invitations
    WHERE wholesaler_id = target_wholesaler_id
       OR used_retailer_id IN (SELECT retailer_id FROM _dc11t4i_target_retailers);

    SELECT residual_rows + count(*) INTO residual_rows
    FROM information_schema.schemata
    WHERE schema_name = target_schema;

    IF residual_rows <> 0 THEN
        RAISE EXCEPTION 'STOP post-cleanup residual count %', residual_rows;
    END IF;

    RAISE NOTICE 'DC11T4I_TEST001_CLEANUP_MODE=REMOVED_CONFIRMED_TEST001';
    RAISE NOTICE 'DC11T4I_TEST001_CLEANUP_APPLY_REQUESTED=%', apply_requested;
END
$dc11t4i_cleanup$;

\if :dc11t4i_apply
COMMIT;
\echo DC11T4I_TEST001_CLEANUP_TX=COMMIT
\else
ROLLBACK;
\echo DC11T4I_TEST001_CLEANUP_TX=ROLLBACK
\endif
