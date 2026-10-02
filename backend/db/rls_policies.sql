-- =============================================================================
-- SIMAP - Row-Level Security (aislamiento entre empresas / tenants)
--
-- ### ARCHIVO DE REFERENCIA - NO SE EJECUTA ###
--
-- Describe las politicas del modelo COMPLETO (las ocho tablas multiempresa de
-- las fases F1 a F4). Quien las aplica de verdad es Alembic, una migracion por
-- fase, junto a las tablas que protegen:
--
--   F1  alembic/versions/20260925_0001_fundamentos_empresas_usuarios.py
--       -> empresas, usuarios, intentos_login
--   F2+ pendientes: activos, lecturas_horometro, alertas, ordenes_trabajo,
--       repuestos, componentes
--
-- Los roles y la extension pgcrypto se crean en db/roles.sql, que SI se
-- ejecuta al inicializar el contenedor (ver docker-compose.yml).
--
-- Mantener este archivo al dia al escribir cada migracion: es el mapa completo
-- que permite revisar el aislamiento de un vistazo, sin leer seis migraciones.
--
-- Transcrito de Arquitectura_SIMAP.pdf, seccion 5.1, extendido a las ocho
-- tablas multiempresa y endurecido segun 04-fase1-fundamentos.md, seccion 6.3.
--
-- La aplicacion fija app.empresa_id en cada transaccion (SET LOCAL) a partir
-- del empresa_id firmado dentro del JWT. Nunca desde un valor del cliente.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Roles
--
-- Hay TRES niveles, y la diferencia entre ellos es lo que sostiene el
-- aislamiento entero:
--
--   superusuario (el POSTGRES_USER de la imagen, 'simap')
--       Ignora RLS SIEMPRE. Ni ENABLE ni FORCE le afectan: es semantica de
--       PostgreSQL y no hay forma de evitarlo. Solo para administrar.
--   simap_owner  -> dueno de las tablas, SIN superusuario y SIN BYPASSRLS
--       Corre las migraciones. Como no es superusuario, FORCE ROW LEVEL
--       SECURITY SI le aplica: tampoco el dueno ve otras empresas.
--   app_user     -> el que usa el backend
--       No es dueno de nada, no puede crear objetos, no tiene BYPASSRLS.
--
-- POR QUE IMPORTA: si el backend conecta con el superusuario o con el dueno de
-- las tablas, las politicas de abajo quedan inertes y el aislamiento entre
-- empresas no existe, sin ningun error que lo delate. Tener el dueno separado
-- del superusuario es lo que hace que FORCE deje de ser decorativo.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'simap_owner') THEN
        CREATE ROLE simap_owner LOGIN PASSWORD 'changeme_owner' NOSUPERUSER NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'changeme' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE simap TO simap_owner, app_user;
GRANT USAGE ON SCHEMA public TO simap_owner, app_user;
GRANT CREATE ON SCHEMA public TO simap_owner;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- Para las tablas que cree simap_owner en migraciones futuras.
ALTER DEFAULT PRIVILEGES FOR ROLE simap_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
-- Y para las que cree el superusuario (p. ej. este mismo script).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- app_user no necesita crear objetos: las migraciones corren con simap_owner.
REVOKE CREATE ON SCHEMA public FROM app_user;

-- -----------------------------------------------------------------------------
-- 2. Activacion de RLS
--
-- ENABLE activa las politicas; FORCE las aplica TAMBIEN al dueno de la tabla.
-- Sin FORCE, cualquier conexion con el rol propietario ve todas las empresas.
-- -----------------------------------------------------------------------------
ALTER TABLE empresas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios            ENABLE ROW LEVEL SECURITY;
ALTER TABLE componentes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE activos             ENABLE ROW LEVEL SECURITY;
ALTER TABLE lecturas_horometro  ENABLE ROW LEVEL SECURITY;
ALTER TABLE alertas             ENABLE ROW LEVEL SECURITY;
ALTER TABLE ordenes_trabajo     ENABLE ROW LEVEL SECURITY;
ALTER TABLE repuestos           ENABLE ROW LEVEL SECURITY;

ALTER TABLE empresas            FORCE ROW LEVEL SECURITY;
ALTER TABLE usuarios            FORCE ROW LEVEL SECURITY;
ALTER TABLE componentes         FORCE ROW LEVEL SECURITY;
ALTER TABLE activos             FORCE ROW LEVEL SECURITY;
ALTER TABLE lecturas_horometro  FORCE ROW LEVEL SECURITY;
ALTER TABLE alertas             FORCE ROW LEVEL SECURITY;
ALTER TABLE ordenes_trabajo     FORCE ROW LEVEL SECURITY;
ALTER TABLE repuestos           FORCE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 3. Politicas de aislamiento
--
-- current_setting('app.empresa_id', true) usa el segundo argumento (missing_ok)
-- para devolver NULL en vez de lanzar error cuando la variable no esta fijada.
-- Una comparacion contra NULL es falsa, asi que una transaccion que olvide el
-- SET LOCAL no ve NINGUNA fila. Falla cerrado, que es lo que queremos: sin el
-- missing_ok la consulta reventaria con un 500 y, peor, invitaria a alguien a
-- "arreglarlo" quitando la politica.
-- -----------------------------------------------------------------------------

-- empresas no tiene empresa_id: la fila ES la empresa, se filtra por id.
CREATE POLICY tenant_isolation_empresas ON empresas
    USING (id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_usuarios ON usuarios
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_componentes ON componentes
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_activos ON activos
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_lecturas ON lecturas_horometro
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_alertas ON alertas
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_ordenes ON ordenes_trabajo
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

CREATE POLICY tenant_isolation_repuestos ON repuestos
    USING (empresa_id = NULLIF(current_setting('app.empresa_id', true), '')::UUID);

-- orden_repuesto no lleva empresa_id; queda protegida transitivamente porque
-- solo es alcanzable a traves de ordenes_trabajo y repuestos (ambas con RLS).

-- -----------------------------------------------------------------------------
-- 3b. Alta administrativa de empresa
--
-- Cuando una politica declara USING y omite WITH CHECK, PostgreSQL usa la misma
-- expresion para validar los INSERT. Eso haria imposible el alta: al crear
-- una empresa todavia no hay app.empresa_id que fijar, porque el id aun no
-- existe. Esta politica adicional permite el INSERT (las politicas permisivas
-- se combinan con OR) sin abrir la lectura: seguir viendo la fila requiere
-- pasar tenant_isolation_empresas.
--
-- OJO AL "TO simap_owner": es lo que hace que crear una empresa NO sea una
-- operacion posible desde la web. SIMAP se cobra por equipo monitoreado, asi
-- que una empresa no puede darse de alta a si misma; el alta la ejecuta quien
-- opera SIMAP con `python -m app.cli crear-empresa`, que conecta con este rol.
-- app_user, el rol con el que el backend atiende cada peticion HTTP, no tiene
-- ninguna politica que le permita insertar aqui, y con RLS activo una operacion
-- sin politica aplicable se deniega. Es decir: aunque alguien reintrodujera por
-- descuido un endpoint de registro, la base lo rechazaria.
--
-- El flujo del alta es: insertar la empresa, fijar app.empresa_id con el id
-- recien generado y solo entonces insertar su primer usuario administrador,
-- que ya pasa tenant_isolation_usuarios.
--
-- Version anterior (revision 0001), abierta a cualquiera, retirada por la 0002:
--     CREATE POLICY empresa_signup ON empresas FOR INSERT WITH CHECK (true);
-- -----------------------------------------------------------------------------
CREATE POLICY empresa_alta_administrativa ON empresas
    FOR INSERT TO simap_owner WITH CHECK (true);

-- -----------------------------------------------------------------------------
-- 4. Registro de intentos de login
--
-- 04-fase1-fundamentos.md, seccion 2: el registro basico de intentos de login
-- entra ya en F1, aunque la auditoria formal sea de F5. La tabla NO lleva RLS
-- por empresa: un intento fallido puede venir de un correo que no existe en
-- ninguna empresa, asi que no hay tenant al que atribuirlo. Solo el backend
-- escribe aqui; nadie la lee desde la API en esta fase.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intentos_login (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correo      TEXT NOT NULL,
    ip          INET,
    exitoso     BOOLEAN NOT NULL,
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intentos_login_correo_fecha
    ON intentos_login (correo, fecha DESC);

-- Esta tabla se crea DESPUES del GRANT ON ALL TABLES de la seccion 1, que solo
-- alcanza a las tablas existentes en ese momento. Hay que concederlo aparte.
GRANT SELECT, INSERT ON intentos_login TO app_user;

-- -----------------------------------------------------------------------------
-- 5. Transferencia de propiedad al rol sin privilegios
--
-- Va al FINAL para que alcance a todas las tablas, incluida intentos_login.
--
-- POR QUE: hasta aqui las tablas pertenecen al usuario que ejecuto el script,
-- que en la imagen de Docker es superusuario. Un superusuario ignora RLS pase
-- lo que pase, asi que mientras el dueno sea superusuario el FORCE de la
-- seccion 2 no protege de nada: es decorativo.
--
-- Al pasar la propiedad a simap_owner (NOSUPERUSER, NOBYPASSRLS), FORCE empieza
-- a aplicarse de verdad tambien al dueno. A partir de aqui solo el superusuario
-- ve todas las empresas, y el superusuario no debe usarse mas que para
-- administrar la base.
--
-- Las migraciones de Alembic deben correr como simap_owner, no como el
-- superusuario, para que las tablas nuevas nazcan con el dueno correcto.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO simap_owner', t.tablename);
    END LOOP;
END
$$;
