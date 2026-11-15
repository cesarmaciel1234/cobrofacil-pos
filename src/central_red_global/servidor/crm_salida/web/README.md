# Subcarpeta web (Mini Web de Enlace con la Nube y API Local)

## Qué hace la carpeta
Esta subcarpeta contiene la interfaz web moderna (SPA nativa sin frameworks externos) y el servidor HTTP local ligero encargado de brindar al usuario una pantalla moderna para autenticarse, configurar el enlace con la nube de Render + Neon DB, validar que el nombre de la sucursal sea **obligatorio**, y visualizar en tiempo real si el sistema está **CONECTADO** o si hubo un error para activar el botón **RECONECTAR**.

---

## Qué funciones tiene (Nombres Reales)

### En `servidor_web.py`:
* `iniciar_servidor_web() -> int`: Arranca un servidor `ThreadingHTTPServer` en localhost (`127.0.0.1`) buscando un puerto libre a partir del 8120. Devuelve el número de puerto activo.
* `detener_servidor_web() -> None`: Apaga el servidor HTTP limpiamente liberando los sockets.
* `obtener_url_web() -> str`: Devuelve la URL canónica (ej. `http://127.0.0.1:8120/`) asegurando que el servidor esté activo.
* `MiniWebHandler`: Manejador HTTP para servir:
  * `GET /`: Devuelve `templates/index.html`.
  * `GET /static/*`: Sirve `estilo.css` y `app.js`.
  * `GET /api/estado`: Devuelve el JSON de telemetría y conectividad actual generado por `estado_nube`.
  * `POST /api/conectar`: Valida campos (exige obligatoriamente `sucursal`), ejecuta `probar_conexion()` contra Render, guarda en `config.json`, despierta el vigilante y devuelve el nuevo estado.
  * `POST /api/reconectar`: Reintenta conectar con las credenciales guardadas.
  * `POST /api/sincronizar`: Invoca `pedir_vuelta()` para forzar un envío inmediato sin esperar el intervalo de 15 minutos.
  * `POST /api/desconectar`: Desvincula las credenciales.

---

## Cómo funciona (Orden de Ejecución)

```
1. El usuario presiona el botón "Empresa del CRM" en la ventana del Servidor de Tienda.
   │
   ├──> crm.py invoca obtener_url_web()
   │       └── iniciar_servidor_web() levanta ThreadingHTTPServer en 127.0.0.1:8120
   │
2. Se abre la ventana moderna (QWebEngineView o navegador predeterminado).
   │
   ├──> GET / -> Carga index.html, estilo.css y app.js
   └──> GET /api/estado -> Consulta a estado_nube y rellena los campos en pantalla
   │
3. El usuario completa los datos y presiona [Conectar]:
   │
   ├──> JS valida que el campo "Nombre de Sucursal" no esté vacío (OBLIGATORIO).
   ├──> POST /api/conectar envía el JSON al servidor local.
   ├──> Backend valida sucursal y ejecuta probar_conexion(url, usuario, password).
   │       ├── Si Render responde OK:
   │       │     - Guarda en config.json
   │       │     - Marca estado "CONECTADO" (badge verde pulsante)
   │       │     - Lanza sincronización en segundo plano con pedir_vuelta()
   │       └── Si Render o la red fallan:
   │             - Marca estado "ERROR" (alerta roja)
   │             - Habilita el botón "RECONECTAR"
   │             - La tienda local continúa cobrando sin ninguna afectación.
```

---

## Qué devuelve cuando falla

* **Nombre de sucursal vacío:** Devuelve HTTP 400 con `{"ok": false, "error": "El nombre de la sucursal es obligatorio...", "campo": "sucursal"}`. En pantalla, el campo de sucursal se resalta en rojo con un mensaje explícito.
* **Credenciales incorrectas (401/403):** Devuelve HTTP 400 con el motivo del rechazo devuelto por Render. El banner cambia a rojo y se muestra el botón **Reconectar**.
* **Falla de conexión a internet o Render dormido (502/503/504):** Devuelve HTTP 400 con la advertencia de timeout. La pantalla instruye a esperar o presionar "Reconectar", recalcando que el POS local no se ve afectado.

---

## Qué NO debe cambiar una mejora futura

1. **Obligatoriedad del nombre de la sucursal:** No permitir conectar a la nube sin nombre de sucursal. Es la clave de particionamiento multi-tienda en la base de datos de Render/Neon DB.
2. **Localhost exclusivo:** El servidor web debe vincularse estrictamente a `127.0.0.1` para prevenir exposición no deseada fuera de la máquina local.
3. **Cero dependencias de CDNs externas:** HTML, CSS y JS deben ser autosuficientes y locales. Si no hay conexión a internet, la página debe abrir y renderizar de forma instantánea.
