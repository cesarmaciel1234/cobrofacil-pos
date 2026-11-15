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

  // Renderizar estado visual
  function renderEstado(data) {
    if (!data) return;

    // Campos de telemetría
    if (valUltimoEnvio) valUltimoEnvio.textContent = data.ultimo_envio || "Sin envíos recientes";
    if (valFilas) valFilas.textContent = `${data.filas_totales || 0} filas (${data.tablas_totales || 0} tablas)`;
    if (valEmpresa) valEmpresa.textContent = data.empresa || "—";
    if (valSucursal) valSucursal.textContent = data.sucursal ? `#${data.sucursal_id || '1'} ${data.sucursal}` : "—";

    // Rellenar campos si el usuario no los está editando
    if (document.activeElement !== urlInput && data.url) {
      urlInput.value = data.url;
    }
    if (document.activeElement !== empresaInput && data.empresa) {
      empresaInput.value = data.empresa;
    }
    if (document.activeElement !== sucursalIdInput && data.sucursal_id) {
      sucursalIdInput.value = data.sucursal_id;
    }
    if (document.activeElement !== sucursalInput && data.sucursal) {
      sucursalInput.value = data.sucursal;
    }
    if (data.tiene_clave_guardada && !passwordInput.value) {
      passwordInput.placeholder = "•••••••• (Contraseña guardada)";
    }

    // Estado del banner
    statusBanner.className = "status-pill-banner";
    const estado = data.estado_texto || (data.conectado ? "conectado" : "desconectado");

    if (estado === "conectado") {
      statusBanner.classList.add("conectado");
      statusTitle.textContent = "● CONECTADO A LA NUBE";
      statusDesc.textContent = `Enlace activo con ${data.empresa || 'empresa'} (${data.sucursal || 'sucursal'}). El negocio sigue vendiendo localmente.`;
      errorBox.classList.remove("active");
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

  // Cargar estado inicial
  async function cargarEstado() {
    try {
      const res = await fetch("/api/estado");
      if (res.ok) {
        const data = await res.json();
        renderEstado(data);
      }
    } catch (err) {
      console.warn("No se pudo obtener estado:", err);
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

      if (data.sucursales && data.sucursales.length > 0) {
        const primera = data.sucursales[0];
        if (!sucursalInput.value) sucursalInput.value = primera.nombre || "";
        if (!sucursalIdInput.value) sucursalIdInput.value = primera.id || "1";
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

  // Botón Sincronizar Ahora
  btnSincronizar.addEventListener("click", async () => {
    btnSincronizar.disabled = true;
    btnSincronizar.textContent = "⏳ Enviando...";
    try {
      const resp = await fetch("/api/sincronizar", { method: "POST" });
      const data = await resp.json();
      if (data.ok) {
        statusDesc.textContent = "Sincronización en proceso en segundo plano (el servidor sigue vendiendo sin pausas).";
      }
    } catch (err) {
      console.warn("Error forzando sincronización:", err);
    } finally {
      setTimeout(() => {
        btnSincronizar.disabled = false;
        btnSincronizar.textContent = "⚡ Sincronizar Ahora";
        cargarEstado();
      }, 3000);
    }
  });

  // Carga inicial y polling periódico cada 5 segundos
  cargarEstado();
  setInterval(cargarEstado, 5000);
});
