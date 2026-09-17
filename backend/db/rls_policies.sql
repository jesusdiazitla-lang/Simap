-- =============================================================================
-- SIMAP - Row-Level Security (aislamiento entre empresas / tenants)
-- Transcrito de Arquitectura_SIMAP.pdf, seccion 5.1, y extendido a las ocho
-- tablas multiempresa como indica el documento.
--
-- La aplicacion fija app.empresa_id en cada transaccion (SET LOCAL) a partir
-- del empresa_id firmado dentro del JWT. Nunca desde un valor del cliente.
-- =============================================================================

ALTER TABLE empresas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios            ENABLE ROW LEVEL SECURITY;
ALTER TABLE componentes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE activos             ENABLE ROW LEVEL SECURITY;
ALTER TABLE lecturas_horometro  ENABLE ROW LEVEL SECURITY;
ALTER TABLE alertas             ENABLE ROW LEVEL SECURITY;
ALTER TABLE ordenes_trabajo     ENABLE ROW LEVEL SECURITY;
ALTER TABLE repuestos           ENABLE ROW LEVEL SECURITY;

-- empresas no tiene empresa_id: la fila ES la empresa, se filtra por id.
CREATE POLICY tenant_isolation_empresas ON empresas
    USING (id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_usuarios ON usuarios
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_componentes ON componentes
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_activos ON activos
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_lecturas ON lecturas_horometro
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_alertas ON alertas
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_ordenes ON ordenes_trabajo
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

CREATE POLICY tenant_isolation_repuestos ON repuestos
    USING (empresa_id = current_setting('app.empresa_id')::UUID);

-- orden_repuesto no lleva empresa_id; queda protegida transitivamente porque
-- solo es alcanzable a traves de ordenes_trabajo y repuestos (ambas con RLS).
