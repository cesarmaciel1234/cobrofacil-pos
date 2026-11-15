"""Letras de góndola. Referencia visual: Admin → Etiquetas de góndola.

Tablas: QFont Bold en la celda (Consolas para id, Segoe UI para nombre y plata).
Títulos y KPIs: QSS weight 900 solo en QLabel.
Nunca QSS 900 y setBold en el mismo widget: en Windows se pintan letras dobles.
No usar en `src/cajero`.
"""

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTableWidgetItem

QSS_TITULO = "font-size: 24px; font-weight: 900; letter-spacing: 1px;"
QSS_KPI = "font-size: 26px; font-weight: 900; letter-spacing: -0.5px;"
QSS_ROTULO = "font-size: 11px; font-weight: 900; letter-spacing: 1px;"


def fuente_id(px: int = 10) -> QFont:
    f = QFont("Consolas", px)
    f.setBold(True)
    return f


def fuente_nombre(px: int = 11) -> QFont:
    f = QFont("Segoe UI", px)
    f.setBold(True)
    return f


def fuente_numero(px: int = 11) -> QFont:
    return fuente_nombre(px)


def vestir_id(item, px: int = 10, tam: int | None = None):
    t = tam if tam is not None else px
    item.setFont(fuente_id(t))
    return item


def vestir_nombre(item, px: int = 11, tam: int | None = None):
    t = tam if tam is not None else px
    item.setFont(fuente_nombre(t))
    return item


def vestir_numero(item, px: int = 11, tam: int | None = None):
    t = tam if tam is not None else px
    item.setFont(fuente_numero(t))
    return item
