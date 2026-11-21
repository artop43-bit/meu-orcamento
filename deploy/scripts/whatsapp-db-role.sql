-- Execute no banco do Hub como administrador, após as migrações da Mensageria.
-- O papel começa sem login. Defina a senha e libere o login separadamente.
\set ON_ERROR_STOP on
BEGIN;

DO $role$
DECLARE
    connector pg_roles%ROWTYPE;
BEGIN
    SELECT * INTO connector FROM pg_roles WHERE rolname = 'hub_whatsapp';
    IF NOT FOUND THEN
        CREATE ROLE hub_whatsapp NOLOGIN;
    ELSIF connector.rolsuper OR connector.rolcreaterole OR connector.rolcreatedb
        OR connector.rolreplication OR connector.rolbypassrls
        OR EXISTS (SELECT FROM pg_auth_members WHERE member = connector.oid)
    THEN
        RAISE EXCEPTION 'O papel hub_whatsapp existente tem privilégios incompatíveis';
    END IF;
END
$role$;
GRANT CONNECT ON DATABASE :"DBNAME" TO hub_whatsapp;
GRANT USAGE ON SCHEMA public TO hub_whatsapp;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.messaging_auth_keys TO hub_whatsapp;

-- A API usa outras chaves dessa tabela. O conector só precisa da versão do WhatsApp Web.
GRANT SELECT, INSERT, UPDATE ON public.messaging_connector_kv TO hub_whatsapp;
ALTER TABLE public.messaging_connector_kv ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS whatsapp_web_version ON public.messaging_connector_kv;
CREATE POLICY whatsapp_web_version ON public.messaging_connector_kv
    TO hub_whatsapp
    USING (key = 'wa_version')
    WITH CHECK (key = 'wa_version');

COMMIT;
