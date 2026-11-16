# Subcarpeta motor (Motores de Transporte Nube: Subida, Bajada y Estado)

## Qué hace la carpeta
Esta subcarpeta alberga la lógica de transporte de datos entre el Servidor de Tienda local y el CRM en la nube alojado en Render (`crm-frigorifico.onrender.com`) con base de datos Neon DB (PostgreSQL serverless).
Gestiona:
1. **Subida:** Replicación segura hacia la nube de clientes, ventas, tickets y tablas base.
2. **Bajada:** Infraestructura de consulta e ingesta en staging de novedades provenientes del CRM central (precios actualizados, nuevos clientes, promociones, reglas de fiado).
3. **Estado:** Registro y persistencia del estado en vivo (Conectado, Conectando, Error, Desconectado, telemetría de filas y tablas).

Opera en aislamiento absoluto respecto al hilo de ventas y al Servidor MariaDB. Si la nube o la conexión a internet fallan, el negocio sigue trabajando localmente sin pausas.

---

## Qué funciones tiene (Nombres Reales)

### En `subida.py`:
* `leer_clientes(ruta_db: str) -> list[dict]`: Lee la tabla `clientes` de `punpro.db` o réplica en modo solo lectura (`mode=ro`).
* `huella(clientes: list[dict], marca: str) -> str`: Genera un hash SHA-256 para detectar si la cartera de clientes sufrió alteraciones.
* `manifiesto(ruta_db: str) -> str`: Genera el hash global SHA-256 de todas las tablas exportables de la base de datos local.
* `leer_base(ruta_db: str)`: Generador iterativo que lee tabla por tabla en SQLite `mode=ro`, sanitizando y anulando columnas con nombres o valores sensibles (`password`, `token`, `secret`, `api_key`).
* `_pedir(abridor, req, timeout, intentos=4)`: Wrapper HTTP con reintentos para soportar los cold starts de Render (errores 502, 503, 504) con backoff exponencial suave.
* `subir_base(...) -> dict`: Al enlazar, manda la venta del día entera y después el resto en lotes de 150 filas hacia `/api/pos/base/tabla`.
* `resolver_empresa(crm_url, api_key, nombre) -> str`: Convierte el slug/nombre comercial de la empresa en su ID numérico en la nube.
* `entrar(crm_url, usuario, password) -> tuple[opener, empresa_id]`: Autentica al usuario contra `/auth/login` y entrega la cookie jar de sesión.
* `probar_conexion(crm_url, usuario, password, api_key) -> tuple[bool, str, str]`: Prueba rápida de conectividad y credenciales utilizada por la mini web.
* `enviar(crm_url, api_key, clientes, ...) -> dict`: Realiza el POST del lote de clientes hacia `/api/pos/clientes/lote`.
* `main() -> int`: Punto de entrada CLI para la ejecución como subproceso desprendido (`--crm-cartera`).

### En `bajada.py`:
* `consultar_novedades_nube(crm_url, api_key, empresa_id, sucursal_id, desde_timestamp) -> dict`: Consulta al CRM por actualizaciones pendientes para la sucursal.
* `recibir_precios_centralizados(crm_url, api_key, ...) -> list[dict]`: Obtiene listas de precios modificados en la nube.
* `recibir_clientes_nube(crm_url, api_key, ...) -> list[dict]`: Obtiene altas o modificaciones de clientes generadas en la nube.
* `aplicar_novedades_en_staging(novedades: dict) -> bool`: Almacena las novedades en `locks/novedades_nube_staging.json` sin bloquear tablas en producción.

### En `estado.py`:
* `GestorEstado.get() -> GestorEstado`: Singleton seguro para hilos que centraliza la telemetría.
* `obtener_estado() -> dict`: Devuelve el diccionario de estado actual con información de conectividad, empresa, sucursal y última sincronización.
* `registrar_conectando(url, empresa, sucursal)`: Pasa el estado a `conectando`.
* `registrar_exito(tablas, filas, empresa, sucursal, mensaje)`: Marca `conectado=True` y almacena fecha y contadores.
* `registrar_error(error)`: Marca `conectado=False`, estado `error` y almacena el motivo para el botón "Reconectar".
* `registrar_bajada(detalle)`: Actualiza fecha de la última bajada de datos.

---

## Cómo funciona (Orden de Ejecución)

```
1. Solicitud de Enlace / Reconexión (Mini Web o Vigilante)
   │
   ├──> subida.probar_conexion(url, usuario, password)
   │       ├── POST /auth/login en Render
   │       └── Si ok: estado_nube.registrar_exito(...)
   │           Si fallo: estado_nube.registrar_error(motivo)
   │
2. Envío de Datos (Subida Periódica)
   │
   ├──> subida.leer_base(punpro.db [mode=ro])
   │       ├── Sanitización de campos sensibles
   │       ├── Generación de lotes de 150 filas
   │       └── POST /api/pos/base/tabla (con reintentos 502/503/504)
   │
3. Recepción de Novedades (Bajada en Staging)
   │
   └──> bajada.consultar_novedades_nube(...)
           ├── GET /api/pos/nube/novedades
           └── Si hay cambios: guardar en locks/novedades_nube_staging.json
```

---

## Qué devuelve cuando falla

* **Error de red / Timeout:** `probar_conexion` o `subir_base` capturan `URLError` o `TimeoutError`. `estado_nube` pasa a estado `"error"` con un mensaje claro ("Tiempo de espera agotado" o "Sin conexión"). El servidor de tienda continúa facturando.
* **Credenciales incorrectas (401/403):** Devuelve `(False, "", "Credenciales inválidas")`. La mini web muestra el estado de error y solicita revisar los campos.
* **Render dormido (Cold start):** `_pedir` reintenta automáticamente hasta 4 veces con pausas de 3s, 6s, 9s. Si persiste, registra el aviso y programa el reintento para la siguiente vuelta sin trabar el sistema local.

---

## Qué NO debe cambiar una mejora futura

1. **Aislamiento gráfico:** Esta subcarpeta **nunca debe importar PyQt6 ni dependencias de interfaz**. Debe funcionar 100% de forma autónoma en modo CLI/headless.
2. **Acceso SQLite estrictamente de solo lectura:** La apertura de bases locales para subida siempre debe usar `uri=True` y `mode=ro` (`file:{ruta}?mode=ro`).
3. **Inviolabilidad de la tienda local:** Todo fallo en la nube debe ser contenido dentro del motor sin lanzar excepciones no controladas hacia el hilo de facturación o el servidor LAN.
