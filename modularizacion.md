# Cómo queda modularizado — Ley de Organización Piramidal

Esta es la única nota de arquitectura en la raíz del proyecto. No es la base de un módulo particular ni guarda reglas aisladas de una pantalla.

Cualquier mejora, refactorización o corrección que se realice en el proyecto debe respetar esta estructura piramidal y actualizar su documentación en el mismo cambio.

---

## 1. La Estructura Piramidal (Los 3 Niveles)

El árbol de código se organiza en tres niveles bien definidos:

```
src/
└── base/                         <-- NIVEL 1: Base (agrupa ramas, NO lleva plano.md)
    ├── rama/                     <-- NIVEL 2: Rama propia del módulo (lleva plano.md o punta del piramide.md)
    │   ├── plano.md              <-- Frente y Fondo (de dónde viene, a dónde va, arquitectura de la rama)
    │   ├── pieza_controlador.py
    │   ├── subcarpeta_ui/        <-- NIVEL 3: Subcarpeta funcional (lleva README.md)
    │   │   ├── README.md         <-- Qué hace, qué función cumple, cómo trabaja paso a paso
    │   │   ├── widget.py
    │   │   └── estilo.qss
    │   └── subcarpeta_motor/     <-- NIVEL 3: Subcarpeta de datos/lógica (lleva README.md)
    │       ├── README.md         <-- Qué hace, qué función cumple, cómo trabaja paso a paso
    │       ├── consulta.py
    │       └── proceso.py
```

### Reglas de nivel:
1. **NIVEL 1 — Bases (`base/`):**
   - Agrupan ramas completas. Ejemplos: `src/cajero`, `src/admin`, `src/jefe`, `src/hardware`, `src`.
   - **No llevan `plano.md`**.
   - No guardan piezas sueltas de una rama. Si un archivo `.py` corresponde a una función específica, debe entrar en la carpeta de su rama.
2. **NIVEL 2 — Ramas (`rama/`):**
   - Es la primera carpeta propia del módulo o subsistema.
   - **Lleva obligatoriamente su `plano.md`** (o `punta del piramide.md` en `src/cajero`).
   - Define el frente (lo visible) y el fondo (el motor/persistencia), además de las conexiones de entrada y salida (de dónde viene y a dónde va).
3. **NIVEL 3 — Subcarpetas funcionales (`subcarpeta/`):**
   - Representan un corte específico interno (ej. `ui/`, `motor/`, `red/`, `cache/`, `modelos/`).
   - **Lleva obligatoriamente su `README.md`**.
   - No copia el plano general; documenta con máximo detalle las funciones y clases de esa subcarpeta.

---

## 2. Los 5 Pilares de Todo Documento `.md`

Cualquier desarrollador, colaborador o IA que lea un `plano.md`, un `README.md` o un `punta del piramide.md` debe poder responder estas 5 preguntas sin necesidad de rastrear el código a ciegas:

| Pilar | Pregunta clave | Qué debe documentar |
| :--- | :--- | :--- |
| **1. De dónde viene** | ¿Qué lo activa o invoca? | Origen exacto: Tecla de acceso directo (F3, F5, F6, F9, F10, ESC), botón visual, señal Qt (`pyqtSignal`), llamada desde otro módulo, socket de red LAN (puerto), webhook o hilo en segundo plano. |
| **2. A dónde va** | ¿Qué produce y dónde impacta? | Destino de los datos: Pantalla o diálogo receptor, tabla de BD (SQLite `punpro.db` / MariaDB `192.168.0.13`), archivo de estado en `locks/`, socket UDP, servicio HTTP (CRM en la nube) o hardware (impresora/cajón). |
| **3. Qué función cumple** | ¿Cuál es su rol específico? | Responsabilidad clara y delimitada. Nombres reales de clases, métodos, controladores y funciones que ejecutan el trabajo. |
| **4. Cómo trabaja** | ¿Cómo corre internamente? | Flujo secuencial paso a paso: Orden de ejecución, hilos auxiliares (`QThread`, `threading.Thread`), transacciones atómicas (`BEGIN/COMMIT/ROLLBACK`), validaciones, qué devuelve ante éxito y qué devuelve ante error/excepción. |
| **5. Qué NO romper** | ¿Cuáles son sus invariantes? | Reglas inviolables del módulo: Blindaje offline, escalado DPI, tipografías obligatorias, aislamiento de perfiles o tolerancias de red. |

---

## 3. Plantilla Oficial: `plano.md` (Donde arranca la rama)

El archivo `plano.md` se ubica en la raíz de cada rama. Debe seguir esta estructura:

```markdown
# Plano de Rama: [Nombre del Módulo o Subsistema]

**Ubicación de la rama:** `src/[base]/[rama]/`  
**Propósito:** Breve resumen de 2-3 renglones sobre qué resuelve esta rama dentro del TPV.

---

## 1. De dónde viene (Entradas / Triggers)
- **Disparador:** Tecla (ej. `F6`), botón en UI (ej. `btn_conectar`), señal Qt o subproceso.
- **Ruta de entrada:** Archivo y línea de donde proviene la llamada (ej. `src/cajero/main_window.py -> abrir_cobro()`).
- **Parámetros recibidos:** Qué datos necesita para iniciar (ej. `id_venta`, `cliente_id`, `total_a_cobrar`).

---

## 2. Frente (Interfaz Visual)
- **Qué ve el usuario:** Ventanas, diálogos, paneles, botones y tarjetas.
- **Controles y atajos:** Teclas asignadas (`Enter` para confirmar, `ESC` para volver, `Tab` para navegar).
- **Estados visuales:** Cómo se pinta en éxito (`verde`), proceso (`cargando/neutral`) y error (`rojo/alerta`).
- **Qué NO pinta:** Información privada que no deba exponerse (claves, tokens, datos técnicos innecesarios).

---

## 3. Fondo (Lógica y Motores)
- **Controlador principal:** Archivo y clase que comanda la lógica (ej. `controlador.py -> GestorOperacion`).
- **Flujo de ejecución:**
  1. Paso 1: Validación de parámetros.
  2. Paso 2: Lectura o escritura en motor local/base de datos.
  3. Paso 3: Notificación de evento o retorno a la interfaz.
- **Tablas afectadas:** Tablas y columnas tocadas en SQLite / MariaDB (ej. `cuenta_corriente`, `ventas`).
- **Hilos y concurrencia:** Si corre en hilo secundario (`QThread`, `Thread(daemon=True)`) para no congelar la pantalla.

---

## 4. A dónde va (Salidas e Impacto)
- **Destino inmediato:** Ventana siguiente, cierre de diálogo (`accept/reject`), o actualización de saldo.
- **Persistencia:** Dónde queda guardado el resultado (`punpro.db`, `locks/crm_estado.json`, etc.).
- **Replicación / Red:** Si se notifica a la Maestra, a las Esclavas o al CRM en la Nube.

---

## 5. Modo Offline y Resiliencia
- **Comportamiento si se corta Internet o la LAN:** Cómo opera localmente sin conexión externa.
- **Manejo de fallos:** Qué hace ante excepciones (reintentos, fallback a SQLite local, registro en log).
- **Qué devuelve si falla:** Valores por defecto o mensajes seguros para no abortar el flujo del cajero.

---

## 6. Qué NO romper (Invariantes Sagrados)
- Reglas específicas que ninguna refactorización debe alterar (ej. no cambiar tipos de datos, no alterar escalado DPI, no cruzar llamadas directas de memoria con otros perfiles).
```

---

## 4. Plantilla Oficial: `README.md` (En cada subcarpeta)

Cada subcarpeta funcional dentro de una rama debe contener su propio `README.md`:

```markdown
# Subcarpeta: [Nombre de la subcarpeta]

**Ubicación:** `src/[base]/[rama]/[subcarpeta]/`  
**Rol:** Propósito técnico de este corte funcional (ej. Interfaz gráfica nativa, Motor de persistencia, Cliente de red).

---

## 1. Qué hace
Descripción concisa y técnica de las tareas que realiza el código dentro de esta carpeta.

---

## 2. Funciones y Clases Principales
Listado con los nombres reales de los componentes:
- `ClasePrincipal`: Propósito, herencia y responsabilidad.
- `funcion_a(param1, param2) -> TipoRetorno`: Qué hace y qué devuelve.
- `funcion_b(...)`: Qué hace y qué excepciones captura.

---

## 3. Cómo funciona (Flujo interno)
Orden secuencial en que se ejecutan los métodos o scripts de esta subcarpeta:
1. `iniciar()`: Inicializa estados y valida recursos.
2. `procesar()`: Aplica la lógica de transformación o consulta.
3. `finalizar()`: Libera cursores, guarda estado o emite señal de término.

---

## 4. De dónde viene y A dónde va (Conexiones)
- **Viene de:** Subcarpeta o archivo de la rama que invoca esta pieza.
- **Va hacia:** Siguiente pieza, base de datos o interfaz receptora.

---

## 5. Tolerancia a Fallos y Modo Offline
- **Qué devuelve cuando falla:** (ej. devuelve `(False, "motivo", [])` o lista vacía `[]`, nunca levanta excepción no controlada).
- **Manejo de timeouts:** Tiempo límite antes de abortar o recurrir a almacenamiento local.

---

## 6. Qué NO debe cambiar una mejora futura
Invariantes locales del módulo (ej. nunca importar PyQt6 en módulos de motor CLI/headless, mantener nombres de columnas compatibles, no alterar firmas públicas).
```

---

## 5. Reglas Particulares por Perfil

### A. Cajero (`src/cajero/`) — Regla de «Punta del Pirámide»
1. `src/cajero` es una base: **no lleva `plano.md`**.
2. Cada rama o actualización en `src/cajero` se documenta en una nota llamada **`punta del piramide.md`**.
3. **No borrar ni "juntar"** lo que esa nota marca: funciona como bitácora acumulativa y viva de producción masiva. No reemplazarla por un informe de riesgo nuevo.
4. Antes de diagnosticar, editar o dar por lista una versión de `src/cajero`, leer obligatoriamente `src/cajero/README.md` (secciones «Parece un defecto y no se toca» y «Producción»).
5. **No aplicar `src/utils/letra.py` en `src/cajero`** (el cajero mantiene sus propios tamaños táctiles y contrastes operativos).

### B. Jefe (`src/jefe/`)
1. `src/jefe` es una base: **no lleva `plano.md`**.
2. Antes de diagnosticar o editar, leer obligatoriamente `src/jefe/reglas.md`.
3. El tema visual es el global (`estilo_dia.qss` / `estilo_noche.qss`). El antiguo `theme_pro.py` está retirado.
4. El SQLite del nodo portable no se reemplaza por `db_manager`.

### C. Admin, Inventario, Promociones y Reportes
1. Al tocar estos módulos, es obligatorio aplicar tipografía de góndola con `src/utils/letra.py`:
   - ID / Códigos: `Consolas Bold`.
   - Nombres y números: `Segoe UI Bold`.
   - Títulos y KPI: `QLabel` con `font-weight: 900`.

### D. Escalado Global (`src/utils/qt_dpi.py`) — NO TOCAR
- `src/utils/qt_dpi.py` fija `QT_SCALE_FACTOR` de **todo** el proceso (cajero, admin, jefe).
- Si un sector se ve chico (letras, tiles, botones), agrandar **solo en ese módulo**: tipografía local, `setFixedSize`, QSS locales.
- **Prohibido** subir el piso de `layout_scale` ni “arreglar” baja resolución desde `qt_dpi` para un pantallazo, porque altera toda la aplicación.

---

## 6. Aislamiento de Perfiles (Motores de Transporte)

1. **Sin cruce directo de datos:** Ningún perfil (Jefe, Cajero, Admin) debe cruzar información leyendo la memoria o el estado en vivo de otro perfil directamente.
2. **Motores de transporte:** Si un perfil genera información que otro necesita (ej. *Promedios* del Jefe genera costos/precios que el *Cajero* debe usar), deben comunicarse enviando los datos a un "Motor de Transporte" intermedio (ej. Base de Datos SQLite/MariaDB, Motor de Mayoreo, archivos de intercambio).
3. **Resiliencia ante fallos:** Al estar desacoplados, si el motor de un perfil colapsa o entra en error, los demás perfiles siguen operando con normalidad porque leen la última verdad consolidada desde el motor de transporte.

---

## 7. Ecosistemas Autónomos (Frontend y Backend Local)

1. **Ecosistemas Cerrados:** Cuando se crea o modifica un módulo complejo dentro de un perfil (por ejemplo, `paso6_cobro/fiado_en_cobro`), tanto su Interfaz (Frontend) como su lógica de consultas (Backend) deben vivir en estado piramidal **dentro de su propia carpeta**.
2. **Motores Locales:** En lugar de importar interfaces o lógicas desde módulos globales (como `clientes_fiado/interfaz`), el módulo local debe tener su propia carpeta `ui/` con su diseño nativo y su propia carpeta `motor/` con un 'motor local'.
3. **Hilos Autónomos:** El motor local actúa como un hilo autónomo que simplemente le consulta o informa al motor global o base de datos externa, pero la resolución de qué hacer con ese dato y cómo dibujarlo pertenece exclusivamente al ecosistema de la rama.
4. **Cero Dispersión:** No dispersar interfaces visuales de una misma función en rutas diferentes. Todo lo visual que ocurra en el Paso 5 vive en el Paso 5; todo lo del Paso 6, en el Paso 6.

---

## 8. Protocolo de Modificación de Código (Checklist Obligatorio)

Al recibir una tarea o planificar una mejora:

1. [ ] **Lectura previa:** Leer `modularizacion.md`, el `plano.md` de la rama afectada (o `punta del piramide.md` en cajero) y el `README.md` de cada subcarpeta involucrada.
2. [ ] **Ubicación piramidal:**
   - Si se crea una pieza nueva, debe ubicarse dentro de la subcarpeta que corresponda (`ui/`, `motor/`, etc.) de su rama.
   - Si existía un archivo suelto en la base, agruparlo dentro de su carpeta de rama correspondiente.
3. [ ] **Actualización de documentación:**
   - Si se modifica la rama, actualizar su `plano.md` reflejando de dónde viene, a dónde va, qué cambió en el frente y en el fondo.
   - Si se modifica una subcarpeta, actualizar su `README.md` detallando las funciones reales modificadas.
4. [ ] **No crear notas sueltas en la raíz:** Nunca crear archivos como `regla_*.md`, `notas_*.md` o scripts de parchado temporales en la raíz. Toda nota vive en la rama correspondiente.
5. [ ] **Informar en la respuesta:** Indicar explícitamente en qué carpeta y archivo quedó documentado el cambio.
