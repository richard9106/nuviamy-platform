from django.db import migrations


def protect(apps,schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''CREATE FUNCTION nuviamy_portal_signature_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Client form signatures cannot be changed or deleted.' USING ERRCODE='23514'; END; $$;''')
    schema_editor.execute('''CREATE FUNCTION nuviamy_portal_form_protect() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'TRUNCATE' THEN RAISE EXCEPTION 'Client forms cannot be truncated.' USING ERRCODE='23514'; END IF;
      IF EXISTS (SELECT 1 FROM portal_clientintakesignature WHERE assignment_id=OLD.id) THEN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Signed forms cannot be deleted.' USING ERRCODE='23514'; END IF;
        IF NEW.id IS DISTINCT FROM OLD.id OR NEW.practice_id IS DISTINCT FROM OLD.practice_id
        OR NEW.client_id IS DISTINCT FROM OLD.client_id OR NEW.template_id IS DISTINCT FROM OLD.template_id
        OR NEW.template_snapshot IS DISTINCT FROM OLD.template_snapshot OR NEW.answers IS DISTINCT FROM OLD.answers
        OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at OR NEW.status NOT IN ('submitted','reviewed') THEN
          RAISE EXCEPTION 'Signed form contents cannot be changed.' USING ERRCODE='23514';
        END IF;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$;''')
    schema_editor.execute('CREATE TRIGGER portal_signature_reject_mutation BEFORE UPDATE OR DELETE ON portal_clientintakesignature FOR EACH ROW EXECUTE FUNCTION nuviamy_portal_signature_immutable();')
    schema_editor.execute('CREATE TRIGGER portal_signature_reject_truncate BEFORE TRUNCATE ON portal_clientintakesignature FOR EACH STATEMENT EXECUTE FUNCTION nuviamy_portal_signature_immutable();')
    schema_editor.execute('CREATE TRIGGER portal_form_protect_signed BEFORE UPDATE OR DELETE ON portal_clientintakeassignment FOR EACH ROW EXECUTE FUNCTION nuviamy_portal_form_protect();')
    schema_editor.execute('CREATE TRIGGER portal_form_reject_truncate BEFORE TRUNCATE ON portal_clientintakeassignment FOR EACH STATEMENT EXECUTE FUNCTION nuviamy_portal_form_protect();')


def unprotect(apps,schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table,trigger in [('portal_clientintakesignature','portal_signature_reject_mutation'),('portal_clientintakesignature','portal_signature_reject_truncate'),('portal_clientintakeassignment','portal_form_protect_signed'),('portal_clientintakeassignment','portal_form_reject_truncate')]:
        schema_editor.execute(f'DROP TRIGGER {trigger} ON {table};')
    schema_editor.execute('DROP FUNCTION nuviamy_portal_signature_immutable();')
    schema_editor.execute('DROP FUNCTION nuviamy_portal_form_protect();')


class Migration(migrations.Migration):
    dependencies=[('portal','0014_portal_information_and_signatures')]
    operations=[migrations.RunPython(protect,unprotect)]
