"""Integración del botón del Servidor con la Mini Web moderna de enlace Nube & CRM.

Abre la Mini Web desacoplada en una ventana moderna con QWebEngineView
(o en el navegador predeterminado del sistema).
"""

from __future__ import annotations

import logging
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger("servidor.ventana.crm")


def _estilo_ventana_web() -> str:
    return """
    QDialog {
        background: #0B0F19;
    }
    #BarraSuperior {
        background: #0F172A;
        border-bottom: 1px solid #1E293B;
        padding: 8px 16px;
    }
    #TituloBarra {
        color: #F8FAFC;
        font-size: 14px;
        font-weight: 700;
    }
    #SubtituloBarra {
        color: #94A3B8;
        font-size: 11px;
    }
    #BtnNavegador {
        background: #1E293B;
        color: #93C5FD;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
    }
    #BtnNavegador:hover {
        background: #334155;
        color: #FFFFFF;
        border-color: #3B82F6;
    }
    #BtnCerrar {
        background: transparent;
        color: #94A3B8;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
    }
    #BtnCerrar:hover {
        background: #DC2626;
        color: #FFFFFF;
        border-color: #EF4444;
    }
    """


class VentanaMiniWebCRM(QDialog):
    """Ventana moderna que aloja la Mini Web de enlace con la Nube."""

    def __init__(self, parent=None, url_web: str = "http://127.0.0.1:8120") -> None:
        super().__init__(parent)
        self.url_web = url_web
        self.setWindowTitle("Cobro Fácil · Enlace Nube & CRM")
        self.resize(600, 680)
        self.setMinimumSize(480, 520)
        self.setStyleSheet(_estilo_ventana_web())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barra superior con accesos
        barra = QHBoxLayout()
        barra.setContentsMargins(16, 10, 16, 10)
        barra.setSpacing(10)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        lbl_titulo = QLabel("☁️ Enlace Nube & CRM · Servidor de Tienda")
        lbl_titulo.setObjectName("TituloBarra")
        lbl_sub = QLabel("Motor desacoplado: la tienda sigue facturando 100% offline si falla internet")
        lbl_sub.setObjectName("SubtituloBarra")
        info_box.addWidget(lbl_titulo)
        info_box.addWidget(lbl_sub)
        barra.addLayout(info_box, 1)

        btn_browser = QPushButton("🌐 Abrir en Navegador")
        btn_browser.setObjectName("BtnNavegador")
        btn_browser.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browser.clicked.connect(self._abrir_en_navegador)
        barra.addWidget(btn_browser)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("BtnCerrar")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.clicked.connect(self.accept)
        barra.addWidget(btn_cerrar)

        lay.addLayout(barra)

        # Contenedor principal: Panel Nativo moderno 100% confiable y sin fallos de Chromium/GPU
        from src.central_red_global.servidor.ventana.panel_nativo import PanelNativoCRM

        self._panel_nativo = PanelNativoCRM(self)
        self._visor_web = None
        lay.addWidget(self._panel_nativo, 1)

    def _abrir_en_navegador(self) -> None:
        try:
            webbrowser.open(self.url_web)
        except Exception as exc:
            logger.warning(f"No se pudo abrir navegador: {exc}")


def abrir_mini_web(parent=None) -> str:
    """Arranca el servidor web local y muestra la ventana de la Mini Web."""
    from src.central_red_global.servidor.crm_salida.web import obtener_url_web

    url = obtener_url_web()
    ventana = VentanaMiniWebCRM(parent, url)
    ventana.exec()
    return url


def pedir_acceso(parent) -> tuple[str, str, str, str, str] | None:
    """Abre la Mini Web moderna de enlace para el usuario."""
    abrir_mini_web(parent)
    try:
        from src.config import config

        url = str(config.get("crm_url") or "https://crm-frigorifico.onrender.com").strip()
        clave = str(config.get("crm_password") or config.get("crm_api_key") or "").strip()
        empresa = str(config.get("crm_usuario") or config.get("crm_empresa") or "").strip()
        sucursal_id = str(config.get("crm_sucursal_id") or "1").strip()
        sucursal = str(config.get("crm_sucursal") or "").strip()
        if empresa and sucursal:
            return url, clave, empresa, sucursal_id, sucursal
    except Exception:
        pass
    return None


def conectar(win, consola, boton) -> None:
    """Engancha el botón 'Empresa del CRM' para abrir la Mini Web moderna."""

    def _aviso(texto: str, nivel: int = logging.INFO) -> None:
        try:
            consola.escribir(texto, nivel)
        except Exception:
            logger.log(nivel, texto)

    def _al_click() -> None:
        try:
            from src.central_red_global.servidor.crm_salida.web import obtener_url_web

            url_web = obtener_url_web()
            _aviso(f"CRM  abriendo Mini Web moderna en {url_web}")
        except Exception as exc:
            _aviso(f"CRM  error al iniciar servidor web local: {exc}", logging.ERROR)

        abrir_mini_web(win)

        try:
            from src.config import config

            empresa = str(config.get("crm_empresa") or config.get("crm_usuario") or "").strip()
            sucursal = str(config.get("crm_sucursal") or "").strip()
            if empresa and sucursal:
                _aviso(f"CRM  configuración activa: Empresa {empresa}, Sucursal {sucursal}")
        except Exception:
            pass

    boton.clicked.connect(_al_click)
