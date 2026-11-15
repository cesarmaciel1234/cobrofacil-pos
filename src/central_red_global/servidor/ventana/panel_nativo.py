"""Panel nativo moderno para configurar el Enlace Nube & CRM.

Se utiliza cuando QWebEngineView no está disponible en el entorno
(por ejemplo en ejecutables PyInstaller o equipos sin binarios de Chromium),
garantizando una experiencia moderna, idéntica a la mini web, con estado
en tiempo real y validación obligatoria de sucursal.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.central_red_global.servidor.crm_salida.motor.estado import estado_nube
from src.central_red_global.servidor.crm_salida.motor.subida import probar_conexion
from src.utils.letra import fuente_nombre, fuente_numero

logger = logging.getLogger("servidor.ventana.panel_nativo")


class _HilosConexion(QObject):
    """Manejo seguro de señales entre el hilo de red y la interfaz Qt."""

    sig_terminado = pyqtSignal(bool, str, str, str)  # ok, titulo, detalle, empresa_id


def _estilo_panel() -> str:
    return """
    QScrollArea {
        border: none;
        background-color: #0B0F19;
    }
    #ContenedorPrincipal {
        background-color: #0B0F19;
    }
    #TarjetaCuerpo {
        background-color: rgba(17, 24, 39, 0.95);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 24px;
    }
    #BrandBadge {
        background-color: rgba(37, 99, 235, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.3);
        color: #93C5FD;
        border-radius: 12px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    #TituloCabecera {
        color: #F8FAFC;
        font-size: 22px;
        font-weight: 900;
        letter-spacing: -0.5px;
    }
    #SubtituloCabecera {
        color: #94A3B8;
        font-size: 13px;
    }
    #BannerShield {
        background-color: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 10px;
        padding: 12px 14px;
    }
    #ShieldTexto {
        color: #94A3B8;
        font-size: 12px;
        line-height: 1.4;
    }
    #BannerEstado {
        border-radius: 10px;
        padding: 12px 16px;
    }
    #BannerEstado.conectado {
        background-color: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.35);
    }
    #BannerEstado.desconectado {
        background-color: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.35);
    }
    #BannerEstado.neutral {
        background-color: rgba(100, 116, 139, 0.12);
        border: 1px solid rgba(148, 163, 184, 0.25);
    }
    #TituloEstado {
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.5px;
    }
    #TituloEstado.conectado { color: #34D399; }
    #TituloEstado.desconectado { color: #F87171; }
    #TituloEstado.neutral { color: #CBD5E1; }
    #DescEstado {
        font-size: 12px;
        color: #94A3B8;
    }
    #AlertaError {
        background-color: rgba(239, 68, 68, 0.15);
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 8px;
        padding: 10px 14px;
    }
    #AlertaErrorTitulo {
        color: #FCA5A5;
        font-size: 12px;
        font-weight: 700;
    }
    #AlertaErrorTexto {
        color: #FEE2E2;
        font-size: 11px;
    }
    QLabel.etiqueta-campo {
        color: #CBD5E1;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel.ayuda-campo {
        color: #64748B;
        font-size: 11px;
    }
    QLabel.asterisco {
        color: #F87171;
        font-size: 11px;
        font-weight: 700;
    }
    QLineEdit {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #F8FAFC;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: #2563EB;
    }
    QLineEdit:focus {
        border-color: #3B82F6;
        background-color: #0F172A;
    }
    #BtnToggleOjo {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #94A3B8;
        font-size: 14px;
        padding: 6px 12px;
    }
    #BtnToggleOjo:hover {
        background-color: #334155;
        color: #FFFFFF;
    }
    #BtnPrincipal {
        background-color: #2563EB;
        color: #FFFFFF;
        border: none;
        border-radius: 8px;
        padding: 12px;
        font-size: 14px;
        font-weight: 700;
    }
    #BtnPrincipal:hover {
        background-color: #1D4ED8;
    }
    #BtnPrincipal:disabled {
        background-color: #1E3A8A;
        color: #94A3B8;
    }
    #BtnReconectar {
        background-color: #EF4444;
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 700;
    }
    #BtnReconectar:hover {
        background-color: #DC2626;
    }
    #BtnSincronizar {
        background-color: #10B981;
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 700;
    }
    #BtnSincronizar:hover {
        background-color: #059669;
    }
    #CajaTelemetria {
        background-color: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 10px;
    }
    #EtiquetaTelemetria {
        color: #64748B;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    #ValorTelemetria {
        color: #E2E8F0;
        font-size: 12px;
        font-weight: 700;
    }
    """


class PanelNativoCRM(QWidget):
    """Panel de configuración nativo que replica la Mini Web al 100%."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_estilo_panel())
        self._senales = _HilosConexion()
        self._senales.sig_terminado.connect(self._al_terminar_conexion)
        self._en_proceso = False

        self._construir_ui()
        self._cargar_datos_existentes()
        self._refrescar_estado()

        # Temporizador para refrescar telemetría y estado
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refrescar_estado)
        self._timer.start(3500)

    def _construir_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        contenedor = QWidget()
        contenedor.setObjectName("ContenedorPrincipal")
        lay_raiz = QVBoxLayout(contenedor)
        lay_raiz.setContentsMargins(24, 20, 24, 24)
        lay_raiz.setSpacing(16)

        # Header con Badge
        header_box = QVBoxLayout()
        header_box.setSpacing(4)
        header_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        badge_row = QHBoxLayout()
        badge_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_badge = QLabel("☁️ TPV PRO · ENLACE NUBE")
        lbl_badge.setObjectName("BrandBadge")
        badge_row.addWidget(lbl_badge)
        header_box.addLayout(badge_row)

        lbl_titulo = QLabel("Conectar Servidor con la Nube")
        lbl_titulo.setObjectName("TituloCabecera")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_box.addWidget(lbl_titulo)

        lbl_sub = QLabel("Sincronización de catálogo, ventas y cartera de clientes con el CRM")
        lbl_sub.setObjectName("SubtituloCabecera")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_box.addWidget(lbl_sub)
        lay_raiz.addLayout(header_box)

        # Shield de Resiliencia
        shield = QFrame()
        shield.setObjectName("BannerShield")
        shield_lay = QHBoxLayout(shield)
        shield_lay.setContentsMargins(12, 10, 12, 10)
        shield_lay.setSpacing(10)

        lbl_shield_icono = QLabel("🛡️")
        lbl_shield_icono.setStyleSheet("font-size: 20px;")
        shield_lay.addWidget(lbl_shield_icono)

        lbl_shield_texto = QLabel(
            "<b>Arquitectura Aislada y Segura:</b> Si internet se corta o la nube no responde, "
            "el negocio sigue vendiendo y cobrando localmente con normalidad."
        )
        lbl_shield_texto.setObjectName("ShieldTexto")
        lbl_shield_texto.setWordWrap(True)
        shield_lay.addWidget(lbl_shield_texto, 1)
        lay_raiz.addWidget(shield)

        # Tarjeta Principal
        tarjeta = QFrame()
        tarjeta.setObjectName("TarjetaCuerpo")
        t_lay = QVBoxLayout(tarjeta)
        t_lay.setContentsMargins(20, 20, 20, 20)
        t_lay.setSpacing(16)

        # Banner de Estado
        self.banner_estado = QFrame()
        self.banner_estado.setObjectName("BannerEstado")
        b_lay = QHBoxLayout(self.banner_estado)
        b_lay.setContentsMargins(12, 10, 12, 10)
        b_lay.setSpacing(10)

        b_text_box = QVBoxLayout()
        b_text_box.setSpacing(2)
        self.lbl_estado_titulo = QLabel("⚪ NO ENLAZADO")
        self.lbl_estado_titulo.setObjectName("TituloEstado")
        self.lbl_estado_desc = QLabel("Motor desacoplado / Operando 100% offline")
        self.lbl_estado_desc.setObjectName("DescEstado")
        b_text_box.addWidget(self.lbl_estado_titulo)
        b_text_box.addWidget(self.lbl_estado_desc)
        b_lay.addLayout(b_text_box, 1)

        self.btn_reconectar = QPushButton("🔄 Reconectar")
        self.btn_reconectar.setObjectName("BtnReconectar")
        self.btn_reconectar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reconectar.clicked.connect(self._al_click_reconectar)
        self.btn_reconectar.setVisible(False)
        b_lay.addWidget(self.btn_reconectar)

        self.btn_sincronizar = QPushButton("⚡ Sincronizar")
        self.btn_sincronizar.setObjectName("BtnSincronizar")
        self.btn_sincronizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sincronizar.clicked.connect(self._al_click_sincronizar)
        self.btn_sincronizar.setVisible(False)
        b_lay.addWidget(self.btn_sincronizar)
        t_lay.addWidget(self.banner_estado)

        # Caja de Error (oculta por defecto)
        self.caja_error = QFrame()
        self.caja_error.setObjectName("AlertaError")
        ce_lay = QVBoxLayout(self.caja_error)
        ce_lay.setContentsMargins(10, 8, 10, 8)
        ce_lay.setSpacing(4)
        lbl_err_tit = QLabel("⚠️ Error al conectar con la Nube")
        lbl_err_tit.setObjectName("AlertaErrorTitulo")
        self.lbl_err_msg = QLabel("Detalle del error")
        self.lbl_err_msg.setObjectName("AlertaErrorTexto")
        self.lbl_err_msg.setWordWrap(True)
        ce_lay.addWidget(lbl_err_tit)
        ce_lay.addWidget(self.lbl_err_msg)
        self.caja_error.setVisible(False)
        t_lay.addWidget(self.caja_error)

        # Formulario
        # 1. URL CRM
        lbl_url = QLabel("Dirección del CRM (Nube)")
        lbl_url.setProperty("class", "etiqueta-campo")
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("https://crm-frigorifico.onrender.com")
        lbl_url_ayuda = QLabel("Servidor de destino en Render con base de datos Neon DB.")
        lbl_url_ayuda.setProperty("class", "ayuda-campo")
        t_lay.addWidget(lbl_url)
        t_lay.addWidget(self.txt_url)
        t_lay.addWidget(lbl_url_ayuda)

        # 2. Empresa / Usuario
        lbl_emp = QLabel("Nombre de la Empresa / Usuario")
        lbl_emp.setProperty("class", "etiqueta-campo")
        self.txt_empresa = QLineEdit()
        self.txt_empresa.setPlaceholderText("Ej: maciel")
        lbl_emp_ayuda = QLabel("Mismo nombre con el que inicia sesión en la plataforma web.")
        lbl_emp_ayuda.setProperty("class", "ayuda-campo")
        t_lay.addWidget(lbl_emp)
        t_lay.addWidget(self.txt_empresa)
        t_lay.addWidget(lbl_emp_ayuda)

        # 3. Contraseña
        lbl_pwd = QLabel("Contraseña de la Empresa")
        lbl_pwd.setProperty("class", "etiqueta-campo")
        pwd_box = QHBoxLayout()
        pwd_box.setSpacing(8)
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("••••••••")
        self.btn_ojo = QPushButton("👁️")
        self.btn_ojo.setObjectName("BtnToggleOjo")
        self.btn_ojo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ojo.clicked.connect(self._toggle_ojo_password)
        pwd_box.addWidget(self.txt_password, 1)
        pwd_box.addWidget(self.btn_ojo)
        lbl_pwd_ayuda = QLabel("Se almacena protegida en la configuración local y nunca viaja por CLI.")
        lbl_pwd_ayuda.setProperty("class", "ayuda-campo")
        t_lay.addWidget(lbl_pwd)
        t_lay.addLayout(pwd_box)
        t_lay.addWidget(lbl_pwd_ayuda)

        # 4. Sucursal (ID y Nombre Obligatorio)
        fila_suc = QHBoxLayout()
        fila_suc.setSpacing(12)

        caja_id = QVBoxLayout()
        caja_id.setSpacing(4)
        lbl_suc_id = QLabel("ID")
        lbl_suc_id.setProperty("class", "etiqueta-campo")
        self.txt_sucursal_id = QLineEdit("1")
        self.txt_sucursal_id.setMaximumWidth(80)
        caja_id.addWidget(lbl_suc_id)
        caja_id.addWidget(self.txt_sucursal_id)
        fila_suc.addLayout(caja_id)

        caja_nom = QVBoxLayout()
        caja_nom.setSpacing(4)
        lbl_suc_nom_box = QHBoxLayout()
        lbl_suc_nom = QLabel("Nombre de Sucursal")
        lbl_suc_nom.setProperty("class", "etiqueta-campo")
        lbl_suc_oblig = QLabel("* Obligatorio")
        lbl_suc_oblig.setProperty("class", "asterisco")
        lbl_suc_nom_box.addWidget(lbl_suc_nom)
        lbl_suc_nom_box.addWidget(lbl_suc_oblig)
        lbl_suc_nom_box.addStretch(1)

        self.txt_sucursal = QLineEdit()
        self.txt_sucursal.setPlaceholderText("Ej: Casa Central / Sucursal Maciel")
        caja_nom.addLayout(lbl_suc_nom_box)
        caja_nom.addWidget(self.txt_sucursal)
        fila_suc.addLayout(caja_nom, 1)
        t_lay.addLayout(fila_suc)

        lbl_suc_ayuda = QLabel("Requerido para que la nube distinga entre múltiples sucursales de la empresa.")
        lbl_suc_ayuda.setProperty("class", "ayuda-campo")
        t_lay.addWidget(lbl_suc_ayuda)

        # Botón Principal
        self.btn_conectar = QPushButton("🚀 Conectar y Enlazar")
        self.btn_conectar.setObjectName("BtnPrincipal")
        self.btn_conectar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_conectar.clicked.connect(self._al_click_conectar)
        t_lay.addWidget(self.btn_conectar)

        # Telemetría Grid (4 cajas)
        tele_box = QHBoxLayout()
        tele_box.setSpacing(8)

        self.lbl_tele_envio = self._crear_caja_telemetria("ÚLTIMO ENVÍO", "—", tele_box)
        self.lbl_tele_filas = self._crear_caja_telemetria("DATOS", "0 filas", tele_box)
        self.lbl_tele_empresa = self._crear_caja_telemetria("EMPRESA", "—", tele_box)
        self.lbl_tele_sucursal = self._crear_caja_telemetria("SUCURSAL", "—", tele_box)
        t_lay.addLayout(tele_box)

        lay_raiz.addWidget(tarjeta)

        # Footer
        lbl_foot = QLabel("Cobro Fácil 2026 · <b>Motor Desacoplado de Transporte Nube</b> · 100% Autónomo")
        lbl_foot.setStyleSheet("color: #475569; font-size: 11px;")
        lbl_foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_raiz.addWidget(lbl_foot)

        scroll.setWidget(contenedor)

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.addWidget(scroll)

    def _crear_caja_telemetria(self, titulo: str, inicial: str, layout: QHBoxLayout) -> QLabel:
        frame = QFrame(self)
        frame.setObjectName("CajaTelemetria")
        flay = QVBoxLayout(frame)
        flay.setContentsMargins(6, 6, 6, 6)
        flay.setSpacing(2)

        lbl_tit = QLabel(titulo, frame)
        lbl_tit.setObjectName("EtiquetaTelemetria")
        lbl_val = QLabel(inicial, frame)
        lbl_val.setObjectName("ValorTelemetria")
        flay.addWidget(lbl_tit)
        flay.addWidget(lbl_val)
        layout.addWidget(frame, 1)
        return lbl_val

    def _toggle_ojo_password(self) -> None:
        if self.txt_password.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_ojo.setText("🔒")
        else:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_ojo.setText("👁️")

    def _cargar_datos_existentes(self) -> None:
        try:
            from src.config import config

            url = str(config.get("crm_url") or "https://crm-frigorifico.onrender.com").strip()
            empresa = str(config.get("crm_usuario") or config.get("crm_empresa") or "").strip()
            pwd = str(config.get("crm_password") or config.get("crm_api_key") or "").strip()
            suc_id = str(config.get("crm_sucursal_id") or "1").strip()
            suc = str(config.get("crm_sucursal") or "").strip()

            self.txt_url.setText(url)
            self.txt_empresa.setText(empresa)
            if pwd:
                self.txt_password.setText(pwd)
            self.txt_sucursal_id.setText(suc_id)
            self.txt_sucursal.setText(suc)
        except Exception as exc:
            logger.debug(f"Error cargando config inicial: {exc}")

    def _refrescar_estado(self) -> None:
        if self._en_proceso:
            return
        est = estado_nube.obtener_estado()
        activo = est.get("enlace_activo", False)
        error = est.get("ultimo_error", "")
        empresa = est.get("empresa", "")
        sucursal = est.get("sucursal", "")
        ultimo_envio = est.get("ultimo_envio_exitoso")
        filas = est.get("filas_enviadas", 0)

        # Actualizar Telemetría
        self.lbl_tele_envio.setText(ultimo_envio[-8:] if ultimo_envio else "—")
        self.lbl_tele_filas.setText(f"{filas} filas")
        self.lbl_tele_empresa.setText(empresa or "—")
        self.lbl_tele_sucursal.setText(sucursal or "—")

        if activo:
            self.banner_estado.setProperty("class", "conectado")
            self.lbl_estado_titulo.setProperty("class", "conectado")
            self.lbl_estado_titulo.setText("● ENLACE ACTIVO / CONECTADO")
            self.lbl_estado_desc.setText(f"Sucursal #{est.get('sucursal_id', '1')} {sucursal} vinculada con {empresa}")
            self.btn_reconectar.setVisible(False)
            self.btn_sincronizar.setVisible(True)
            self.caja_error.setVisible(False)
        elif error:
            self.banner_estado.setProperty("class", "desconectado")
            self.lbl_estado_titulo.setProperty("class", "desconectado")
            self.lbl_estado_titulo.setText("⚠️ ERROR DE ENLACE / DESCONECTADO")
            self.lbl_estado_desc.setText(str(error)[:75] + ("..." if len(str(error)) > 75 else ""))
            self.btn_reconectar.setVisible(True)
            self.btn_sincronizar.setVisible(False)
            self.caja_error.setVisible(True)
            self.lbl_err_msg.setText(str(error))
        else:
            self.banner_estado.setProperty("class", "neutral")
            self.lbl_estado_titulo.setProperty("class", "neutral")
            self.lbl_estado_titulo.setText("⚪ NO ENLAZADO")
            self.lbl_estado_desc.setText("Motor desacoplado / Operando 100% offline")
            self.btn_reconectar.setVisible(False)
            self.btn_sincronizar.setVisible(False)
            self.caja_error.setVisible(False)

        # Refrescar estilo de Qt
        self.banner_estado.style().unpolish(self.banner_estado)
        self.banner_estado.style().polish(self.banner_estado)
        self.lbl_estado_titulo.style().unpolish(self.lbl_estado_titulo)
        self.lbl_estado_titulo.style().polish(self.lbl_estado_titulo)

    def _al_click_conectar(self) -> None:
        url = self.txt_url.text().strip().rstrip("/")
        empresa = self.txt_empresa.text().strip()
        password = self.txt_password.text().strip()
        sucursal_id = self.txt_sucursal_id.text().strip() or "1"
        sucursal = self.txt_sucursal.text().strip()

        if not sucursal:
            self._mostrar_error_local("El nombre de la sucursal es obligatorio.")
            self.txt_sucursal.setFocus()
            return

        if not url:
            self._mostrar_error_local("Falta la dirección URL del CRM.")
            self.txt_url.setFocus()
            return

        if not empresa:
            self._mostrar_error_local("Falta el nombre de la empresa / usuario.")
            self.txt_empresa.setFocus()
            return

        if not password:
            try:
                from src.config import config

                password = str(config.get("crm_password") or config.get("crm_api_key") or "").strip()
            except Exception:
                pass
            if not password:
                self._mostrar_error_local("Debe ingresar la contraseña de la empresa.")
                self.txt_password.setFocus()
                return

        self._iniciar_proceso_conexion(url, empresa, password, sucursal_id, sucursal)

    def _al_click_reconectar(self) -> None:
        self._al_click_conectar()

    def _al_click_sincronizar(self) -> None:
        try:
            from src.central_red_global.servidor.crm_salida.vigilante import pedir_vuelta

            pedir_vuelta()
            self.lbl_estado_desc.setText("Sincronización manual solicitada al vigilante...")
        except Exception as exc:
            logger.warning(f"Error pidiendo sincronización: {exc}")

    def _mostrar_error_local(self, msg: str) -> None:
        self.caja_error.setVisible(True)
        self.lbl_err_msg.setText(msg)
        self.banner_estado.setProperty("class", "desconectado")
        self.lbl_estado_titulo.setProperty("class", "desconectado")
        self.lbl_estado_titulo.setText("⚠️ VALIDACIÓN REQUERIDA")
        self.lbl_estado_desc.setText(msg)
        self.banner_estado.style().unpolish(self.banner_estado)
        self.banner_estado.style().polish(self.banner_estado)

    def _iniciar_proceso_conexion(
        self, url: str, empresa: str, password: str, sucursal_id: str, sucursal: str
    ) -> None:
        self._en_proceso = True
        self.btn_conectar.setEnabled(False)
        self.btn_conectar.setText("⏳ Conectando con la Nube...")
        self.btn_reconectar.setEnabled(False)
        self.caja_error.setVisible(False)

        self.banner_estado.setProperty("class", "neutral")
        self.lbl_estado_titulo.setProperty("class", "neutral")
        self.lbl_estado_titulo.setText("⏳ PROBANDO CONEXIÓN...")
        self.lbl_estado_desc.setText("Contactando a Render y autenticando sucursal...")
        self.banner_estado.style().unpolish(self.banner_estado)
        self.banner_estado.style().polish(self.banner_estado)

        estado_nube.registrar_conectando(url, empresa, sucursal)

        def _tarea_fondo() -> None:
            ok, empresa_id, detalle, sucursales = probar_conexion(url, empresa, password)
            if ok:
                nombre_sucursal = sucursal
                suc_id = sucursal_id
                if sucursales:
                    coincidente = next(
                        (
                            s
                            for s in sucursales
                            if str(s.get("id")) == str(sucursal_id)
                            or str(s.get("nombre", "")).strip().lower() == sucursal.strip().lower()
                        ),
                        None,
                    )
                    if coincidente:
                        suc_id = str(coincidente.get("id", sucursal_id))
                        nombre_sucursal = str(coincidente.get("nombre") or sucursal)

                try:
                    from src.config import config

                    config.set("crm_url", url)
                    config.set("crm_usuario", empresa)
                    config.set("crm_password", password)
                    config.set("crm_empresa", empresa)
                    if empresa_id:
                        config.set("crm_empresa_id", empresa_id)
                    config.set("crm_sucursal_id", suc_id)
                    config.set("crm_sucursal", nombre_sucursal)
                except Exception as exc:
                    logger.warning(f"Error guardando config CRM: {exc}")

                estado_nube.registrar_exito(
                    empresa=empresa,
                    sucursal=nombre_sucursal,
                    mensaje=f"Enlazado correctamente a {url}. Empresa: {empresa}, Sucursal: #{suc_id} {nombre_sucursal}.",
                )
                try:
                    from src.central_red_global.servidor.crm_salida.vigilante import pedir_vuelta

                    pedir_vuelta()
                except Exception:
                    pass
                self._senales.sig_terminado.emit(True, "Conectado", f"Enlazado con éxito a #{suc_id} {nombre_sucursal}", str(empresa_id or ""))
            else:
                detalle_usuario = detalle
                if "incorrectos" in detalle.lower() or "no se pudo entrar" in detalle.lower():
                    detalle_usuario = "Usuario o contraseña incorrectos en Render. Por favor verifique las credenciales."
                elif "timed out" in detalle.lower() or "timeout" in detalle.lower():
                    detalle_usuario = "Render tardó en despertar (Cold Start). Aguarde 10 segundos y pulse Reconectar."
                elif any(c in detalle for c in ("502", "503", "504")):
                    detalle_usuario = "Render está iniciando el contenedor. Aguarde unos segundos y pulse Reconectar."
                estado_nube.registrar_error(detalle_usuario)
                self._senales.sig_terminado.emit(False, "Error de enlace", detalle_usuario, "")

        t = threading.Thread(target=_tarea_fondo, daemon=True)
        t.start()

    def _al_terminar_conexion(self, ok: bool, titulo: str, detalle: str, empresa_id: str) -> None:
        self._en_proceso = False
        self.btn_conectar.setEnabled(True)
        self.btn_conectar.setText("🚀 Conectar y Enlazar")
        self.btn_reconectar.setEnabled(True)
        self._refrescar_estado()
