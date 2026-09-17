-- =============================================================================
-- SIMAP - Esquema de base de datos (PostgreSQL 16)
-- Transcrito de Arquitectura_SIMAP.pdf, seccion 4. Fuente de verdad del modelo.
-- Las migraciones de Alembic deben converger a este esquema.
--
-- Cada tabla que pertenece a una empresa lleva su propia columna empresa_id,
-- incluso las que ya la heredan por otra tabla: es intencional, para que cada
-- politica RLS filtre directamente por empresa_id sin resolver relaciones.
-- =============================================================================

-- Extension necesaria para generar UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE empresas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre          TEXT NOT NULL,
    fecha_registro  DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE usuarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresas(id),
    nombre          TEXT NOT NULL,
    correo          TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    rol             TEXT NOT NULL CHECK (rol IN
                        ('operario','supervisor','tecnico_taller','gerente','administrador')),
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE componentes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresas(id),
    nombre          TEXT NOT NULL,
    descripcion     TEXT
);

CREATE TABLE activos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id          UUID NOT NULL REFERENCES empresas(id),
    nombre              TEXT NOT NULL,
    tipo                TEXT,
    ubicacion           TEXT,
    criticidad          TEXT CHECK (criticidad IN ('alta','media','baja')),
    qr_code             TEXT NOT NULL UNIQUE,
    horometro_actual    INTEGER NOT NULL DEFAULT 0,
    fecha_ultima_falla  DATE
);

CREATE TABLE lecturas_horometro (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id       UUID NOT NULL REFERENCES empresas(id),
    activo_id        UUID NOT NULL REFERENCES activos(id),
    registrado_por   UUID NOT NULL REFERENCES usuarios(id),
    valor_horometro  INTEGER NOT NULL,
    fecha            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alertas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresas(id),
    activo_id       UUID NOT NULL REFERENCES activos(id),
    reportado_por   UUID NOT NULL REFERENCES usuarios(id),
    sintoma         TEXT NOT NULL,
    nota            TEXT,
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN
                        ('pendiente','revisada','descartada','convertida_en_orden')),
    fecha           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ordenes_trabajo (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id           UUID NOT NULL REFERENCES empresas(id),
    activo_id            UUID NOT NULL REFERENCES activos(id),
    componente_id        UUID NOT NULL REFERENCES componentes(id),
    alerta_origen_id     UUID REFERENCES alertas(id),
    reportado_por        UUID NOT NULL REFERENCES usuarios(id),
    reparado_por         UUID REFERENCES usuarios(id),
    autorizado_por       UUID REFERENCES usuarios(id),
    horometro_en_falla   INTEGER NOT NULL,
    temperatura          NUMERIC(5,2),
    codigo_error         TEXT,
    descripcion          TEXT,
    estado               TEXT NOT NULL DEFAULT 'reportada' CHECK (estado IN
                             ('reportada','en_taller','reparada','cerrada')),
    trabajo_realizado    TEXT,
    fecha_falla          TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_salida_taller  TIMESTAMPTZ
);

CREATE TABLE repuestos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      UUID NOT NULL REFERENCES empresas(id),
    nombre          TEXT NOT NULL,
    codigo          TEXT,
    stock_actual    INTEGER NOT NULL DEFAULT 0,
    stock_minimo    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE orden_repuesto (
    orden_id     UUID NOT NULL REFERENCES ordenes_trabajo(id),
    repuesto_id  UUID NOT NULL REFERENCES repuestos(id),
    cantidad     INTEGER NOT NULL CHECK (cantidad > 0),
    PRIMARY KEY (orden_id, repuesto_id)
);

-- Indices recomendados
CREATE INDEX idx_activos_empresa   ON activos(empresa_id);
CREATE INDEX idx_ordenes_activo    ON ordenes_trabajo(activo_id);
CREATE INDEX idx_ordenes_estado    ON ordenes_trabajo(estado);
CREATE INDEX idx_horometro_activo  ON lecturas_horometro(activo_id, fecha);
