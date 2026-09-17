# Grafo de dependencias - Backend (FastAPI)

> Generado automáticamente por `python tools/graph/graph.py build`. No editar a mano.

```mermaid
graph LR
  subgraph api[api]
    app_api["api"]
    app_api_v1["api.v1"]
    app_api_v1_router["api.v1.router"]
    app_api_v1_routes["api.v1.routes"]
    app_api_v1_routes_health["api.v1.routes.health"]
  end
  subgraph app[app]
    app["app"]
  end
  subgraph core[core]
    app_core["core"]
    app_core_config["core.config"]
  end
  subgraph db[db]
    app_db["db"]
  end
  subgraph jobs[jobs]
    app_jobs["jobs"]
  end
  subgraph main[main]
    app_main["main"]
  end
  subgraph models[models]
    app_models["models"]
  end
  subgraph schemas[schemas]
    app_schemas["schemas"]
    app_schemas_health["schemas.health"]
  end
  subgraph services[services]
    app_services["services"]
  end
  app_api_v1_router --> app_api_v1_routes_health
  app_api_v1_routes_health --> app_core_config
  app_api_v1_routes_health --> app_schemas_health
  app_main --> app_api_v1_router
  app_main --> app_core_config
```
