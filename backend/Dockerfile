# Imagen del backend SIMAP (docs/contexto/02-arquitectura.md, seccion 6)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000

# Proxies cuya cabecera X-Forwarded-For se cree (05-fase2, seccion 8.4). La API vive detras de los
# rewrites de Next y del proxy del hosting: si no se cree a ninguno, el limite de login por IP ve la
# IP del proxy para todos y una sola persona bloquea a todas. Si se cree a cualquiera ("*"), un
# cliente se inventa la cabecera y esquiva el limite. En el despliegue, poner la IP o la red del
# proxy real; uvicorn la lee de esta variable.
ENV FORWARDED_ALLOW_IPS=127.0.0.1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
