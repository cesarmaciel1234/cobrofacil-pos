// Mini Web Enlace CRM - Controlador SPA Moderno

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("form-enlace");
  const urlInput = document.getElementById("url");
  const empresaInput = document.getElementById("empresa");
  const passwordInput = document.getElementById("password");
  const sucursalIdInput = document.getElementById("sucursal_id");
  const sucursalInput = document.getElementById("sucursal");

  const btnConectar = document.getElementById("btn-conectar");
  const btnReconectar = document.getElementById("btn-reconectar");
  const btnSincronizar = document.getElementById("btn-sincronizar");
  const togglePwdBtn = document.getElementById("toggle-pwd");

  const statusBanner = document.getElementById("status-banner");
  const statusTitle = document.getElementById("status-title");
  const statusDesc = document.getElementById("status-desc");
  const errorBox = document.getElementById("error-box");
  const errorMsg = document.getElementById("error-msg");

  const valUltimoEnvio = document.getElementById("val-ultimo-envio");
  const valFilas = document.getElementById("val-filas");
  const valEmpresa = document.getElementById("val-empresa");
  const valSucursal = document.getElementById("val-sucursal");
  let datosCargadosInicialmente = false;

  // Mostrar / Ocultar contraseña
  if (togglePwdBtn) {
    togglePwdBtn.addEventListener("click", () => {
      const actual = passwordInput.getAttribute("type");
      if (actual === "password") {
        passwordInput.setAttribute("type", "text");
        togglePwdBtn.textContent = "🔒";
      } else {
        passwordInput.setAttribute("type", "password");
        togglePwdBtn.textContent = "👁️";
      }
    });
  }

    // Quitar borde de error al escribir en contraseña o sucursal
    passwordInput.addEventListener("input", () => {
      passwordInput.classList.remove("input-error");
      if (errorBox.classList.contains("active") && errorMsg.textContent.toLowerCase().includes("contrase")) {
        errorBox.classList.remove("active");
      }
    });

    sucursalInput.addEventListener("input", () => {
      sucursalInput.classList.remove("input-error");
      if (errorBox.classList.contains("active") && errorMsg.textContent.includes("sucursal")) {
        errorBox.classList.remove("active");
      }
    });

  const CLAVE_COPIA = "enlace-nube-estado";

  function leerCopia() {
    try {
      const crudo = localStorage.getItem(CLAVE_COPIA);
      return crudo ? JSON.parse(crudo) : null;
    } catch (err) {
      return null;
    }
  }

  function guardarCopia(data) {
    if (!data || typeof data !== "object") return;
    const copia = Object.assign({}, data);
    delete copia.password;
    delete copia.crm_password;
    try {
      localStorage.setItem(CLAVE_COPIA, JSON.stringify(copia));
    } catch (err) {}
  }

  function avisarOffline() {
    if (!statusBanner) return;
    statusBanner.className = "status-pill-banner desconectado";
    if (statusTitle) statusTitle.textContent = "🛡️ MOTOR DESACOPLADO";
    if (statusDesc) statusDesc.textContent = "Motor desacoplado / Operando 100% offline. La caja sigue vendiendo.";
    if (errorBox) errorBox.classList.remove("active");
  }

  function despertarNube(url) {
    const base = String(url || "").trim().replace(/\/$/, "");
    if (!base) return Promise.resolve();
    const corte = new AbortController();
    const reloj = setTimeout(() => corte.abort(), 8000);
    return fetch(base + "/health", { mode: "no-cors", cache: "no-store", signal: corte.signal })
      .catch(() => {})
      .finally(() => clearTimeout(reloj));
  }

  // Renderizar estado visual
  function renderEstado(data) {
    if (!data) return;

    // Campos de telemetría
    if (valUltimoEnvio) {
      const marca = data.ultimo_envio || "Sin envíos recientes";
      const anterior = data.ultimo_error && String(data.ultimo_error).toLowerCase().indexOf("mariadb") >= 0;
      valUltimoEnvio.textContent = anterior ? (marca + " · anterior") : marca;
    }
    if (valFilas) valFilas.textContent = `${data.filas_totales || 0} filas (${data.tablas_totales || 0} tablas)`;
    if (valEmpresa) valEmpresa.textContent = data.empresa || "—";
    if (valSucursal) valSucursal.textContent = data.sucursal ? `#${data.sucursal_id || '1'} ${data.sucursal}` : "—";

    // Rellenar campos SOLO en la primera carga o si están vacíos para no pisar lo que escribe el usuario
    const pc = String(data.nombre_pc || "").trim();
    const guardada = String(data.sucursal || "").trim();
    if (guardada) {
      sucursalInput.value = guardada;
      sucursalInput.readOnly = true;
      if (data.sucursal_id) sucursalIdInput.value = data.sucursal_id;
    } else if (pc) {
      sucursalInput.value = pc;
      sucursalInput.readOnly = true;
    }
    if (!datosCargadosInicialmente) {
      if (data.url) urlInput.value = data.url;
      if (data.empresa) empresaInput.value = data.empresa;
      datosCargadosInicialmente = true;
    } else {
      if (!urlInput.value && data.url) urlInput.value = data.url;
      if (!empresaInput.value && data.empresa) empresaInput.value = data.empresa;
    }
    const mismaPc = data.nombre_pc && String(data.sucursal || "").trim().toLowerCase() === String(data.nombre_pc).trim().toLowerCase();
    if (mismaPc && data.sucursal_id) sucursalIdInput.value = data.sucursal_id;
    if (data.tiene_clave_guardada && !passwordInput.value) {
      passwordInput.placeholder = "•••••••• (Contraseña guardada)";
    }

    // Estado del banner
    statusBanner.className = "status-pill-banner";
    const estado = data.estado_texto || (data.conectado ? "conectado" : "desconectado");

    if (estado === "conectado") {
      statusBanner.classList.add("conectado");
      statusTitle.textContent = "● CONECTADO A LA NUBE";
      statusDesc.textContent = data.ultimo_error
        ? (data.mensaje || data.ultimo_error)
        : `Enlace activo con ${data.empresa || 'empresa'} (${data.sucursal || 'sucursal'}). El negocio sigue vendiendo localmente.`;
      if (data.ultimo_error) {
        errorBox.classList.add("active");
        errorMsg.textContent = data.ultimo_error;
      } else {
        errorBox.classList.remove("active");
      }
      btnReconectar.style.display = "none";
      btnSincronizar.style.display = "inline-flex";
      btnConectar.textContent = "Actualizar Enlace";
    } else if (estado === "error") {
      statusBanner.classList.add("error");
      statusTitle.textContent = "⚠️ ERROR DE ENLACE / DESCONECTADO";
      statusDesc.textContent = data.ultimo_error || data.mensaje || "Ocurrió un error al contactar la nube.";
      errorBox.classList.add("active");
      errorMsg.textContent = data.ultimo_error || data.mensaje || "Error de conexión.";
      btnReconectar.style.display = "inline-flex";
      btnSincronizar.style.display = "none";
      btnConectar.textContent = "Volver a Conectar";
    } else if (estado === "conectando") {
      statusBanner.classList.add("conectando");
      statusTitle.textContent = "⏳ CONECTANDO...";
      statusDesc.textContent = data.mensaje || "Estableciendo conexión y validando credenciales...";
      btnReconectar.style.display = "none";
    } else {
      statusBanner.classList.add("desconectado");
      statusTitle.textContent = "⚪ NO ENLAZADO";
      statusDesc.textContent = "Ingrese los datos de la empresa y la sucursal obligatoria para enlazar con la nube.";
      errorBox.classList.remove("active");
      btnReconectar.style.display = "none";
      btnSincronizar.style.display = "none";
      btnConectar.textContent = "🚀 Conectar y Enlazar";
    }
  }

  // Cargar estado. La copia local ya está pintada; esto solo la refresca.
  async function cargarEstado() {
    try {
      const res = await fetch("/api/estado");
      if (!res.ok) throw new Error("estado");
      const data = await res.json();
      guardarCopia(data);
      renderEstado(data);
    } catch (err) {
      avisarOffline();
    }
  }

  // Enviar formulario (Conectar)
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const url = urlInput.value.trim();
    const empresa = empresaInput.value.trim();
    const password = passwordInput.value.trim();
    const sucursal_id = sucursalIdInput.value.trim() || "1";
    const sucursal = sucursalInput.value.trim();

    // VALIDACIÓN OBLIGATORIA: Nombre de la sucursal obligatorio
    if (!sucursal) {
      sucursalInput.classList.add("input-error");
      sucursalInput.focus();
      errorBox.classList.add("active");
      errorMsg.textContent = "El nombre de la sucursal es obligatorio para identificar este punto de venta en la nube.";
      return;
    }

    if (!empresa) {
      empresaInput.classList.add("input-error");
      empresaInput.focus();
      errorBox.classList.add("active");
      errorMsg.textContent = "Debe indicar el nombre de la empresa / usuario registrado en el CRM.";
      return;
    }

    // UI Loading
    btnConectar.disabled = true;
    btnConectar.textContent = "⏳ Conectando...";
    statusBanner.className = "status-pill-banner conectando";
    statusTitle.textContent = "⏳ CONECTANDO CON LA NUBE...";
    statusDesc.textContent = "Validando credenciales en Render / Neon DB (puede demorar unos segundos si el contenedor está despertando)...";
    errorBox.classList.remove("active");

    try {
      const resp = await fetch("/api/conectar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, empresa, password, sucursal_id, sucursal }),
      });
      const data = await resp.json();

      if (!resp.ok || !data.ok) {
        throw new Error(data.error || "Fallo de conexión");
      }

      if (data.sucursal_id) sucursalIdInput.value = data.sucursal_id;
      if (data.sucursal && !data.nombre_pc) sucursalInput.value = data.sucursal;
      if (data.estado) {
        data.estado.nombre_pc = data.estado.nombre_pc || (document.getElementById("sucursal") && sucursalInput.value);
        if (data.sucursal_id) data.estado.sucursal_id = data.sucursal_id;
        if (data.sucursal) data.estado.sucursal = data.sucursal;
      }
      renderEstado(data.estado);
    } catch (err) {
      errorBox.classList.add("active");
      errorMsg.textContent = err.message || "Error al conectar.";
      statusBanner.className = "status-pill-banner error";
      statusTitle.textContent = "⚠️ ERROR DE CONEXIÓN";
      statusDesc.textContent = err.message || "Fallo de conexión.";
      btnReconectar.style.display = "inline-flex";
    } finally {
      btnConectar.disabled = false;
      btnConectar.textContent = "Actualizar Enlace";
    }
  });

  // Botón Reconectar
  btnReconectar.addEventListener("click", async () => {
    btnReconectar.disabled = true;
    btnReconectar.textContent = "⏳ Reconectando...";
    statusBanner.className = "status-pill-banner conectando";
    statusTitle.textContent = "⏳ REINTENTANDO CONEXIÓN...";
    statusDesc.textContent = "Verificando enlace con el CRM en la nube...";

    try {
      const resp = await fetch("/api/reconectar", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        throw new Error(data.error || "No se pudo reconectar");
      }
      renderEstado(data.estado);
    } catch (err) {
      errorBox.classList.add("active");
      errorMsg.textContent = err.message || "Fallo al reconectar.";
      statusBanner.className = "status-pill-banner error";
      statusTitle.textContent = "⚠️ ERROR AL RECONECTAR";
      statusDesc.textContent = err.message;
    } finally {
      btnReconectar.disabled = false;
      btnReconectar.textContent = "🔄 Reconectar";
    }
  });

  // Botón Sincronizar Ahora: despierta Render y pide el empuje de lo nuevo.
  if (btnSincronizar) btnSincronizar.addEventListener("click", async () => {
    if (!navigator.onLine) {
      avisarOffline();
      return;
    }
    const texto = btnSincronizar.textContent;
    btnSincronizar.disabled = true;
    btnSincronizar.textContent = "⏳ Enviando...";
    if (statusDesc) statusDesc.textContent = "Despertando la nube y enviando lo nuevo de esta sucursal.";
    try {
      await despertarNube(urlInput.value);
      const sucursalId = (sucursalIdInput.value || "1").trim();
      const resp = await fetch("/api/sincronizar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: (empresaInput.value || "").trim(),
          branch_id: sucursalId,
          sucursal_id: sucursalId,
          last_sync: (leerCopia() || {}).ultimo_envio || "",
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || data.ok === false) throw new Error(data.error || "sin enlace");
      if (statusDesc) statusDesc.textContent = "El envío sigue en segundo plano. La caja no se detiene.";
      await cargarEstado();
    } catch (err) {
      avisarOffline();
    } finally {
      btnSincronizar.disabled = false;
      btnSincronizar.textContent = texto || "⚡ Sincronizar Ahora";
    }
  });

  const copiaInicial = leerCopia();
  if (copiaInicial) renderEstado(copiaInicial);
  cargarEstado();
  setInterval(cargarEstado, 5000);
});
