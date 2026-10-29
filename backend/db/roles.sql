-- =============================================================================
-- SIMAP - Arranque de la base: SOLO roles y extensiones.
--
-- Lo ejecuta el superusuario (POSTGRES_USER) una unica vez, al inicializar el
-- contenedor. NO crea tablas: de eso se encarga Alembic, como exige
-- docs/contexto/04-fase1-fundamentos.md, seccion 4.3 ("ninguna tabla se crea o
-- modifica a mano contra la base de datos").
--
-- POR QUE ESTA SEPARADO: Alembic conecta como simap_owner, asi que ese rol
-- tiene que existir antes. Y la extension pgcrypto se instala aqui porque
-- crearla puede requerir privilegios que simap_owner no tiene.
--
-- Los tres roles y para que sirve cada uno:
--   POSTGRES_USER (superusuario)  Ignora RLS SIEMPRE. Solo administrar.
--   simap_owner                   Dueno de las tablas. Corre las migraciones.
--                                 No es superusuario, asi que FORCE ROW LEVEL
--                                 SECURITY si le aplica.
--   app_user                      El que usa el backend. Ni dueno ni superusuario.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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

-- simap_owner necesita crear objetos (las migraciones). app_user no.
GRANT CREATE ON SCHEMA public TO simap_owner;
REVOKE CREATE ON SCHEMA public FROM app_user;

-- Toda tabla que cree simap_owner queda automaticamente accesible a app_user,
-- sin tener que repetir el GRANT en cada migracion.
ALTER DEFAULT PRIVILEGES FOR ROLE simap_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE simap_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_user;

-- =============================================================================
-- CUARTO ROL: el plano de control (la consola del operador de SIMAP).
--
-- POR QUE UN ROL APARTE Y NO app_user CON UNA BANDERA
-- ---------------------------------------------------
-- El operador de SIMAP no pertenece a ninguna empresa y necesita ver la lista
-- de todas ellas, que es justo lo que el aislamiento existe para impedir.
-- Resolverlo con una bandera en la aplicacion dejaria la frontera a merced de
-- que nadie se equivoque al escribir una consulta. Con un rol de base de datos
-- distinto, la frontera la impone PostgreSQL.
--
-- LA REGLA QUE HACE QUE ESTO SIGA SIENDO CIERTO EN EL FUTURO
-- ----------------------------------------------------------
-- A operador_user se le conceden permisos TABLA POR TABLA, en cada migracion
-- que cree una tabla que deba ver. NUNCA se le pone un ALTER DEFAULT
-- PRIVILEGES como el de app_user. Consecuencia: las tablas de negocio de F2 en
-- adelante (activos, lecturas, alertas, ordenes, repuestos) quedan fuera de su
-- alcance por omision, sin que nadie tenga que acordarse de nada. Hacerlas
-- visibles exigiria un GRANT explicito, que se ve en la revision del codigo.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'operador_user') THEN
        CREATE ROLE operador_user LOGIN PASSWORD 'changeme_operador'
            NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE simap TO operador_user;
GRANT USAGE ON SCHEMA public TO operador_user;
REVOKE CREATE ON SCHEMA public FROM operador_user;

-- =============================================================================
-- QUINTO ROL: el job nocturno de la fase 4 (07-fase4, seccion 7.10).
--
-- Recorre todas las empresas para recalcular su riesgo: necesita saber cuales
-- existen, pero no puede leer sus datos. Es miembro de app_user, asi que hereda
-- sus permisos y sigue sujeto a RLS: solo ve algo despues de fijar el tenant,
-- empresa por empresa. Su unico privilegio propio es ejecutar
-- empresas_activas(), que concede la migracion 0009 y devuelve solo los ids.
--
-- Vive aqui y no en la migracion porque simap_owner no puede crear roles ni
-- conceder pertenencias.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'job_user') THEN
        CREATE ROLE job_user LOGIN PASSWORD 'changeme_job' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;

GRANT app_user TO job_user;
GRANT CONNECT ON DATABASE simap TO job_user;
GRANT USAGE ON SCHEMA public TO job_user;

-- =============================================================================
-- JIT apagado para los roles de la aplicacion (08-fase5, decision 13 y 9.2).
--
-- Con jit = on (lo de fabrica en PostgreSQL 16) las consultas de los indicadores
-- superan el umbral de costo y PostgreSQL compila codigo nativo en cada una:
-- ~1,3 s de CPU para consultas cuyo trabajo real es de decenas de ms. Para
-- consultas cortas y repetidas solo estorba. Vive aqui porque simap_owner no
-- puede alterar roles; solo afecta a las conexiones NUEVAS (reiniciar el pool).
-- =============================================================================

ALTER ROLE app_user SET jit = off;
ALTER ROLE job_user SET jit = off;
