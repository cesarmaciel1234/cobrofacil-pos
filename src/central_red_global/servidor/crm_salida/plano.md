# Plano de la Rama: Enlace Nube & CRM (Espejo Render + Neon DB)

Esta rama es un **satélite desacoplado y autónomo** del Servidor de Tienda.
Su función principal es la réplica continua hacia la nube alojada en Render (`crm-frigorifico.onrender.com`) respaldada por Neon DB (PostgreSQL serverless), y la recepción controlada de datos de la nube (precios, clientes, promociones) hacia la tienda local.

> [!IMPORTANT]
> **Ley de Oro de Autonomía de la Tienda:**
> La tienda física local es la soberana de la verdad operativa. Si la nube falla, se apaga, da error 502/503/504 o se corta la conexión a internet, **la tienda sigue trabajando, vendiendo y cobrando exactamente igual sin pausas ni ventanas de error invasivas**.

---

## Estructura Piramidal de la Rama

```
src/central_red_global/servidor/crm_salida/
├── plano.md                    <-- Este documento (Frente y Fondo de la rama)
├── __init__.py                 <-- Re-exports de alto nivel
├── proceso.py                  <-- Aislamiento de subproceso (CLI)
├── vigilante.py                <-- Orquestador en segundo plano (daemon thread)
├── motor.py                    <-- Módulo puente para compatibilidad absoluta (--crm-cartera y tests)
├── motor/                      <-- Subcarpeta: Motores de Transporte Nube
│   ├── README.md               <-- Documentación detallada del motor
│   ├── __init__.py
│   ├── subida.py               <-- Extracción SQLite ro, sanitización y HTTP POST por lotes
│   ├── bajada.py               <-- Recepción y descarga de novedades desde el CRM central
│   └── estado.py               <-- Telemetría, registro de conexión y persistencia en disco
└── web/                        <-- Subcarpeta: Mini Web Moderna y API REST Local
    ├── README.md               <-- Documentación detallada de la web
    ├── __init__.py
    ├── servidor_web.py         <-- Servidor ThreadingHTTPServer embebido en 127.0.0.1
    ├── static/
    │   ├── estilo.css          <-- Diseño dark mode glassmorphism y animaciones de estado
    │   └── app.js              <-- Controlador SPA: validación, reconexión y telemetría
    └── templates/
        └── index.html          <-- Interfaz HTML5 responsiva y moderna
```

---

## 1. Frente (Lo que ve el usuario)

1. **Botón en la ventana del Servidor de Tienda:**
   * **Ubicación:** Barra inferior de `src/central_red_global/servidor/ventana/lienzo.py`.
   * **Botón:** `[Empresa del CRM]` (o `[Enlace Nube / CRM]`).
   * **Acción:** Al presionar, inicia el servidor web local si no estaba encendido y abre la **Mini Web Moderna** en una ventana estilizada con visor web nativo (o en el navegador predeterminado).

2. **Mini Web Moderna de Enlace:**
   * **Diseño:** Estética moderna oscura con tarjetas de cristal esmerilado (glassmorphism), tipografía nítida y microanimaciones de pulso.
   * **Banner de Estado Dinámico:**
     * `● CONECTADO`: Badge verde esmeralda con halo pulsante indicando que el enlace está activo y sincronizando. Muestra la empresa y sucursal.
     * `⚠️ ERROR DE ENLACE`: Badge carmesí con detalle claro del fallo (ej. contraseña incorrecta, timeout de Render o falta de internet) y botón destacado de **🔄 RECONECTAR**.
     * `⏳ CONECTANDO`: Indicador rotativo mientras valida credenciales.
     * `⚪ NO ENLAZADO`: Estado inicial de espera.
   * **Formulario de Enlace con Bloqueo y Lápiz de Edición:**
     * **Bloqueo Inteligente:** Una vez configurado y enlazado, los campos quedan bloqueados (`read-only`) para evitar modificaciones accidentales en operación diaria.
     * **Botón Lápiz (`✏️ Modificar`):** Permite desbloquear la edición para cambiar contraseña, sucursal o URL, transformando el botón inferior en `🚀 Guardar y Conectar`.
     * **URL del CRM:** Por defecto `https://crm-frigorifico.onrender.com`.
     * **Empresa / Usuario:** Nombre comercial con el que se identifica la cuenta (ej. `maciel`).
     * **Contraseña:** Campo protegido con botón de alternar visibilidad.
     * **ID de Sucursal:** Número identificador (ej. `1`).
     * **Nombre de Sucursal [OBLIGATORIO]:** Campo estrictamente requerido con validación en frontend y backend.
   * **Dashboard de Telemetría Premium (Grilla 3x2):**
     * `🎫 TICKETS ENVIADOS`: Conteo total de tickets y ventas enviadas a la nube.
     * `👥 CLIENTES EN CARTERA`: Cartera de clientes fidelizados sincronizados con el CRM.
     * `📦 CATÁLOGO Y DELTAS`: Filas totales y cambios incrementales de catálogo.
     * `⚡ LATENCIA NUBE`: Round-trip HTTP en tiempo real hacia Render / Neon DB (ej. `● 84 ms`).
     * `⏱️ ÚLTIMA SUBIDA`: Timestamp y duración de la última sincronización.
     * `🏢 SUCURSAL ASIGNADA`: Número y nombre de la sucursal activa.
   * **Botones de Acción:**
     * `[⚡ Sincronizar Ahora con la Nube]`: Botón principal de la barra inferior cuando la configuración está bloqueada/activa.
     * `[🚀 Guardar y Conectar]`: Botón activo cuando se edita con el lápiz.
     * `[Reconectar]`: Visible cuando ocurre un fallo o cold start para reintentar la conexión de inmediato.
   * **Banner de Seguridad:** Aviso visible confirmando que la tienda local trabaja en modo 100% autónomo y blindado.

---

## 2. Fondo (Cómo opera el motor desacoplado)

```
Servidor de Tienda (bandeja.py / headless.py)
   │
   ├──> Mini Web (servidor_web.py en 127.0.0.1:8120)
   │       ├── GET / -> templates/index.html
   │       ├── POST /api/conectar -> subida.probar_conexion()
   │       │                            └── config.set(...) + pedir_vuelta()
   │       └── POST /api/reconectar -> reintento inmediato
   │
   ├──> vigilante.py (hilo daemon en segundo plano)
   │       │
   │       ├──> subida.py (o subproceso proceso.py via `python main.py --crm-cartera`)
   │       │       ├── Lee punpro.db / espejo_tienda.db (SQLite mode=ro estricto)
   │       │       ├── Sanitiza claves secretas (None)
   │       │       ├── Manifiesto SHA-256 (omite envío si la base no cambió)
   │       │       ├── HTTP POST -> el día de venta sale entero; el resto, en lotes de 150
   │       │       ├── Checkpointing progresivo por tabla (persistencia inmediata tras cada tabla ok)
   │       │       └── Actualiza estado_nube (sincronizando, exito o error)
   │       │
   │       └──> bajada.py (recepción de datos de la nube)
   │               ├── GET /api/pos/nube/novedades
   │               └── Guarda en locks/novedades_nube_staging.json
```

1. **Aislamiento por Subproceso y Threads Autónomos:**
   * Las peticiones HTTP a la nube nunca corren en el hilo principal de Qt ni en los sockets de la red local.
   * Se utiliza `vigilante.py` como un hilo daemon desacoplado y `proceso.py` para la subida masiva.
2. **Lectura Solo Lectura Inviolable:**
   * La base local se abre con `file:{ruta}?mode=ro` (URI SQLite). Ninguna operación de réplica bloquea escrituras de MariaDB ni cajeros.
3. **Manejo de Cold Starts en Render:**
   * La función `_pedir` amortigua los arranques en frío (HTTP 502/503/504) con reintentos progresivos de 3s, 6s, 9s.
4. **Arquitectura Bidireccional e Industrial:**
   * `motor/subida.py`: Réplica ascendente de ventas, clientes y tablas base con **checkpointing progresivo por tabla** y medición de latencia HTTP (`medir_latencia`).
   * `motor/bajada.py`: Infraestructura lista para la recepción de precios y clientes desde la nube a través de staging protegido.
   * `vigilante.py`: Event-driven debounce sync (`notificar_venta`) disparado tras cada cobro en caja con circuit breaker y backoff adaptativo.
   * `tablero.py`: Chip visual en tiempo real (`self.chip_nube`) en el panel maestro con estado, filas sincronizadas y latencia en milisegundos.

---

## 3. Qué no hay que romper

1. No importar PyQt6 dentro de `motor/` ni de `web/servidor_web.py`.
2. Mantener `motor.py` en la raíz de la rama exportando las mismas funciones que usaban `main.py` y `tests/test_crm_cartera.py`.
3. No quitar la validación obligatoria del nombre de la sucursal.
4. Mantener siempre la apertura de SQLite en modo solo lectura (`mode=ro`).
5. No tocar `src/utils/qt_dpi.py` (escalado global).
