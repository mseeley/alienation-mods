#!/usr/bin/env python3
"""Desktop editor for save-editor plan files (YAML).

  tools/.venv/bin/python tools/save-editor-gui.py [plan.yaml]

Creates and edits the same plans as tools/save-editor-cli.py and keeps the comments and layout of
hand-written files. Every field has a ? button (or press F1 in it) with its help text. Load a save
to pick items by index, check a plan against a character, or write an edited save.

Validation, field help, perk maths, dumping and writing saves all live in tools/lib/saveedit.py,
shared with the command line. Needs PySide6 and ruamel.yaml (tools/requirements.txt).
"""
import copy
import difflib
import html
import io
import json
import math
import os
import re
import sys
import tempfile
import time

import yaml
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from lib import saveedit as core
from lib.gamedata import EQUIPMENT_NAMES, PRIMARY_CLASS, WEAPON_NAMES
from lib.savedata import ROOT, OutputPathError, check_output_path

EXAMPLES_DIR = os.path.join(ROOT, 'tools', 'example-recipes')
DOCS = os.path.join(ROOT, 'docs', 'save-editor.md')

# --- look ------------------------------------------------------------------------------------------

LABEL_WIDTH = 132        # field-label column, the same in every card so inputs line up
INPUT_INSET = 9          # extra left inset for spin-box text, to line up with line edits and combos
BG, PANEL, CARD, CARD_HI, BORDER = '#0e1116', '#141920', '#1a2029', '#212935', '#2b3442'
TEXT, MUTED, FAINT = '#e6edf3', '#8d99aa', '#5d6878'
ACCENT, ACCENT_DIM, TEAL = '#ff8a3d', '#b85d22', '#3cc8d2'
RARITY_COLOURS = ['#c3cad5', '#4ade80', '#5aa7ff', '#a78bfa', '#ffa040']   # stock, common, uncommon, rare, legendary
LEVEL_COLOURS = {'error': '#f87171', 'untested': '#f472b6', 'warning': '#e8d06a', 'note': MUTED, 'ok': '#4ade80'}
LEVEL_MEANING = {'error': 'error: always blocks saving the savegame',
                 'untested': 'untested: something the game never generates; blocks saving unless '
                             '"Allow untested values" is on (Settings)',
                 'warning': 'warning: a heads-up, never blocks saving'}


def level_legend():
    """One line of rich text explaining the three marks."""
    return '&nbsp;&nbsp;&nbsp;'.join(
        f'<span style="color:{LEVEL_COLOURS[lv]}">{LEVEL_GLYPH[lv]}</span>&nbsp;{label}'
        for lv, label in (('error', 'error'), ('untested', 'untested'), ('warning', 'warning (OK)')))


LEVEL_GLYPH = {'error': '!', 'untested': '▲', 'warning': '✓', 'note': '·', 'ok': '✓'}
SOCKET_COLOURS = {'core1': '#3b8cff', 'core2': '#ff4b4b', 'core3': '#ffd23c', 'core': '#e8ecf1'}
CORE_COLOURS = {1: '#3b8cff', 2: '#ff4b4b', 3: '#ffd23c', 4: '#e8ecf1'}

ITEM_NAMES = {**WEAPON_NAMES, **EQUIPMENT_NAMES}
SECTION_TITLES = {'weapons': 'Weapons', 'equipment': 'Equipment', 'armor_sets': 'Armor sets'}
STAT_TITLES = {'fire_rate': 'Fire rate', 'charge_time': 'Charge time', 'clip_size': 'Clip size',
               'critical_hit_chance': 'Critical hit chance'}
METAL_TITLES = {'stock': 'Stock', 'common': 'Common', 'uncommon': 'Uncommon', 'rare': 'Rare',
                'legendary': 'Legendary', 'unobtainium': 'Unobtainium'}
ARMOR_EFFECT_TITLES = {
    'movement_speed': 'Movement speed', 'max_hp_multiplier': 'Max HP', 'rush_recharge': 'Rush recharge',
    'health_drop_rate': 'Health drop rate', 'ability_drop_rate': 'Ability drop rate',
    'ability_recharge_1': 'Ability 1 recharge (s)', 'ability_recharge_2': 'Ability 2 recharge (s)',
    'ability_recharge_3': 'Ability 3 recharge (s)',
}

STYLE = f"""
* {{ font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {CARD_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}
QSplitter::handle {{ background: {BG}; width: 1px; }}
#Sidebar, #RightPanel {{ background: {PANEL}; }}
#EditorScroll, #EditorHost {{ background: {BG}; border: none; }}
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
#CardTitle {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
#CardSub, #Muted {{ color: {MUTED}; }}
#Faint {{ color: {FAINT}; }}
#PageTitle {{ font-size: 22px; font-weight: 700; }}
#PageSub {{ color: {MUTED}; font-size: 13px; }}
#Derived {{ color: {MUTED}; }}   /* hints worked out from the values; teal is kept for links */
#Banner {{ background: #3a1d1d; color: #ffd0d0; border-radius: 6px; padding: 6px 10px; }}
#SectionHeader {{ color: {FAINT}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#FieldLabel {{ color: #c3ccd8; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 7px; padding: 4px 8px;
    selection-background-color: {ACCENT_DIM}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QSpinBox[warn="true"], QDoubleSpinBox[warn="true"] {{ border: 1px solid {LEVEL_COLOURS['untested']}; color: {LEVEL_COLOURS['untested']}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QAbstractSpinBox QLineEdit {{ border: none; padding: 0; margin: 0; background: transparent; }}
QComboBox {{ padding-left: 10px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; border-color: {CARD}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{ background: {CARD_HI}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM}; outline: none; }}
QPushButton {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 7px; padding: 5px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {CARD_HI}; }}
QPushButton#Danger {{ background: transparent; color: #f87171; border: 1px solid #7f2f2f; }}
QPushButton#Danger:hover {{ background: #3a1a1a; border-color: #f87171; }}
QPushButton#Danger:disabled {{ color: {FAINT}; border-color: {BORDER}; background: transparent; }}
QPushButton#Primary {{ background: {ACCENT}; color: #1a0f05; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #ff9d5c; }}
QPushButton#Primary:disabled {{ background: {CARD}; color: {FAINT}; border: 1px solid {BORDER}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 3px 7px; }}
QToolButton:hover {{ background: {CARD_HI}; border-color: {BORDER}; }}
QToolButton:checked {{ background: {CARD_HI}; border-color: {ACCENT}; }}
QToolButton#Seg {{ border: 1px solid {BORDER}; border-radius: 0; padding: 4px 9px; background: {BG}; color: {MUTED}; }}
QToolButton#Seg:checked {{ background: {CARD_HI}; color: {TEXT}; border-color: {ACCENT}; }}
QToolButton#Seg:hover {{ color: {TEXT}; }}
QToolButton#Help {{ color: {MUTED}; border: 1px solid {BORDER}; border-radius: 10px; min-width: 20px; max-width: 20px;
    min-height: 20px; max-height: 20px; padding: 0; font-weight: 700; font-size: 11px; }}
QToolButton#Help:hover {{ color: {BG}; background: {TEAL}; border-color: {TEAL}; }}
QCheckBox {{ spacing: 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QTreeWidget, QListWidget, QTableWidget {{ background: transparent; border: none; outline: none; }}
QTreeWidget::item, QListWidget::item {{ padding: 5px 4px; border-radius: 6px; }}
QTreeWidget::item:selected {{ background: {CARD_HI}; }}
QListWidget::item:selected {{ background: {CARD_HI}; color: {TEXT}; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {CARD}; }}
QTreeView {{ show-decoration-selected: 0; }}
QTreeView::branch, QTreeView::branch:selected {{ background: transparent; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; padding: 4px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 14px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:right {{ padding: 14px 8px; border-bottom: none; border-left: 2px solid transparent; }}
QTabBar::tab:right:hover {{ color: {TEXT}; }}
QTabBar::tab:right:selected {{ color: {MUTED}; border-bottom: none; border-left: 2px solid transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QMenuBar {{ background: {PANEL}; }}
QMenuBar::item:selected {{ background: {CARD_HI}; }}
QMenu {{ background: {CARD_HI}; border: 1px solid {BORDER}; padding: 4px; border-radius: 8px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; spacing: 6px; padding: 6px 12px; }}
QToolButton#TB {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 7px; padding: 5px 12px; }}
QToolButton#TB:hover {{ border-color: {ACCENT}; }}
QToolButton#TB:disabled {{ color: {FAINT}; }}
QToolButton#TBPrimary {{ background: {ACCENT}; color: #1a0f05; border: none; border-radius: 7px; padding: 6px 12px; font-weight: 600; }}
QToolButton#TBPrimary:hover {{ background: #ff9d5c; }}
QToolButton#TBPrimary:disabled {{ background: {CARD_HI}; color: {FAINT}; border: 1px solid {BORDER}; font-weight: 400; }}
#HelpPopup {{ background: {CARD_HI}; border: 1px solid {TEAL}; border-radius: 10px; }}
"""


def dot_icon(colour, size=12, ring=None):
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor(colour))
    p.setPen(QtGui.QPen(QtGui.QColor(ring), 1.5) if ring else Qt.NoPen)
    p.drawEllipse(QtCore.QRectF(2, 2, size - 4, size - 4))
    p.end()
    return QtGui.QIcon(pm)


def star_icon(colour, size=12):
    """A five-point star in the rarity colour: the sidebar's marker for an equipped item (instead of the dot)."""
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor(colour))
    p.setPen(Qt.NoPen)
    c, outer, inner = size / 2, size / 2, size / 2 * 0.42
    pts = [QtCore.QPointF(c + (outer if k % 2 == 0 else inner) * math.sin(k * math.pi / 5),
                          c + 0.6 - (outer if k % 2 == 0 else inner) * math.cos(k * math.pi / 5)) for k in range(10)]
    p.drawPolygon(QtGui.QPolygonF(pts))
    p.end()
    return QtGui.QIcon(pm)


TINT_ICON = QtCore.QSize(42, 16)


def tint_icon(colours=()):
    """A weapon tint as three side-by-side bands (blank when no colours, to keep the list lined up)."""
    w, h = TINT_ICON.width(), TINT_ICON.height()
    pm = QtGui.QPixmap(w * 2, h * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    if colours:
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        box = QtCore.QRectF(1, 2, w - 2, h - 4)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(box, 3, 3)
        p.setClipPath(clip)
        band = box.width() / len(colours)
        for i, c in enumerate(colours):
            p.fillRect(QtCore.QRectF(box.left() + i * band, box.top(), band + 0.5, box.height()), QtGui.QColor(c))
        p.setClipping(False)
        p.setPen(QtGui.QPen(QtGui.QColor(FAINT), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box, 3, 3)
        p.end()
    return QtGui.QIcon(pm)


class AppStyle(QtWidgets.QProxyStyle):
    """Fusion plus a clearer checkbox: an outlined box that fills with a tick when checked, so a ticked
    box can't be mistaken for a colour swatch."""

    def pixelMetric(self, metric, opt=None, widget=None):
        if metric in (QtWidgets.QStyle.PM_IndicatorWidth, QtWidgets.QStyle.PM_IndicatorHeight,
                      QtWidgets.QStyle.PM_ExclusiveIndicatorWidth, QtWidgets.QStyle.PM_ExclusiveIndicatorHeight):
            return 18
        return super().pixelMetric(metric, opt, widget)

    def drawPrimitive(self, element, opt, p, widget=None):
        if element == QtWidgets.QStyle.PE_IndicatorRadioButton:
            return self._radio(opt, p)
        if element != QtWidgets.QStyle.PE_IndicatorCheckBox:
            return super().drawPrimitive(element, opt, p, widget)
        st = opt.state
        on = bool(st & QtWidgets.QStyle.State_On)
        enabled = bool(st & QtWidgets.QStyle.State_Enabled)
        hover = bool(st & QtWidgets.QStyle.State_MouseOver) and enabled
        r = QtCore.QRectF(opt.rect).adjusted(1.5, 1.5, -1.5, -1.5)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if on:
            fill = QtGui.QColor(ACCENT if enabled else ACCENT_DIM)
            p.setPen(Qt.NoPen)
            p.setBrush(fill.lighter(112) if hover else fill)
            p.drawRoundedRect(r, 4, 4)
            pen = QtGui.QPen(QtGui.QColor('#1a0f05' if enabled else '#3a2414'), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            w, h, x, y = r.width(), r.height(), r.x(), r.y()
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x + w * 0.24, y + h * 0.53),
                                            QtCore.QPointF(x + w * 0.43, y + h * 0.72),
                                            QtCore.QPointF(x + w * 0.77, y + h * 0.31)]))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if hover else ('#5d6878' if enabled else BORDER)), 1.5))
            p.setBrush(QtGui.QColor(BG))
            p.drawRoundedRect(r, 4, 4)
        p.restore()


def _radio(self, opt, p):
    """Radio button: outlined circle; selected = accent circle with a dark centre dot."""
    st = opt.state
    on = bool(st & QtWidgets.QStyle.State_On)
    enabled = bool(st & QtWidgets.QStyle.State_Enabled)
    hover = bool(st & QtWidgets.QStyle.State_MouseOver) and enabled
    r = QtCore.QRectF(opt.rect).adjusted(1.5, 1.5, -1.5, -1.5)
    p.save()
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    if on:
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(ACCENT if enabled else ACCENT_DIM))
        p.drawEllipse(r)
        p.setBrush(QtGui.QColor('#1a0f05'))
        p.drawEllipse(r.center(), r.width() * 0.2, r.height() * 0.2)
    else:
        p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if hover else ('#5d6878' if enabled else BORDER)), 1.5))
        p.setBrush(QtGui.QColor(BG))
        p.drawEllipse(r)
    p.restore()


AppStyle._radio = _radio


def chevron_image(colour, name):
    """A dropdown chevron as a PNG for the stylesheet (Qt's stylesheet draws combo-box arrows itself)."""
    pm = QtGui.QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(colour), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(5, 9), QtCore.QPointF(12, 16), QtCore.QPointF(19, 9)]))
    p.end()
    path = os.path.join(tempfile.gettempdir(), f'alienation-save-editor-{name}.png')
    pm.save(path)
    return path.replace(os.sep, '/')


def apply_theme(app):
    """Style, palette and stylesheet for the whole application."""
    app.setStyle(AppStyle('Fusion'))
    pal = QtGui.QPalette()
    for role, c in ((QtGui.QPalette.Window, BG), (QtGui.QPalette.Base, BG), (QtGui.QPalette.AlternateBase, PANEL),
                    (QtGui.QPalette.Text, TEXT), (QtGui.QPalette.WindowText, TEXT), (QtGui.QPalette.Button, CARD_HI),
                    (QtGui.QPalette.ButtonText, TEXT), (QtGui.QPalette.Highlight, ACCENT_DIM),
                    (QtGui.QPalette.HighlightedText, TEXT), (QtGui.QPalette.ToolTipBase, CARD_HI),
                    (QtGui.QPalette.ToolTipText, TEXT), (QtGui.QPalette.PlaceholderText, FAINT)):
        pal.setColor(role, QtGui.QColor(c))
    app.setPalette(pal)
    arrow, arrow_off = chevron_image(MUTED, 'chevron'), chevron_image(FAINT, 'chevron-off')
    app.setStyleSheet(STYLE + f"""
QComboBox::down-arrow {{ image: url({arrow}); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url({arrow_off}); }}
""")
    app.setWindowIcon(app_icon())                    # also the Dock icon on macOS


def glyph_icon(glyph, colour, size=16):
    """A small coloured text symbol as an icon (e.g. the worst check result on the Checks tab)."""
    pm = QtGui.QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    f = p.font()
    f.setPixelSize(size - 2)
    f.setBold(True)
    p.setFont(f)
    if glyph == '!':                        # errors: a filled disc, so it can't be mistaken for a close button
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(colour))
        p.drawEllipse(QtCore.QRectF(1, 1, size - 2, size - 2))
        p.setPen(QtGui.QColor(BG))
    else:
        p.setPen(QtGui.QColor(colour))
    p.drawText(QtCore.QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    return QtGui.QIcon(pm)


def app_icon_pixmap(size=256):
    """The app icon (drawn on a 256 grid, scaled), also used for the macOS app bundle."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.scale(size / 256, size / 256)
    p.setBrush(QtGui.QColor(PANEL))
    p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 10))
    p.drawEllipse(18, 18, 220, 220)
    for i, c in enumerate(['core1', 'core2', 'core3']):
        p.setPen(QtGui.QPen(QtGui.QColor(SOCKET_COLOURS[c]), 12))
        p.setBrush(QtGui.QColor(BG))
        p.drawEllipse(QtCore.QPointF(78 + i * 50, 128 + (-34 if i == 1 else 18)), 24, 24)
    p.end()
    return pm


def app_icon():
    icon = QtGui.QIcon()
    for size in (32, 64, 128, 256, 512):
        icon.addPixmap(app_icon_pixmap(size))
    return icon


class InputPolish(QtCore.QObject):
    """Qt ignores stylesheet padding inside spin boxes and sizes them taller than the other inputs.
    When a spin box is first polished, give it the same text inset and height as a line edit.
    Also: the mouse wheel never changes a number box, dropdown or slider; it scrolls the page instead,
    so scrolling past a field can't edit it by accident."""
    height = None

    @staticmethod
    def wheel_field(obj):
        """The number box / dropdown / slider a wheel event landed on (its inner text box counts), or None."""
        w = obj if isinstance(obj, QtWidgets.QWidget) else None
        for _ in range(3):
            if w is None:
                return None
            if isinstance(w, (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox, QtWidgets.QAbstractSlider)) \
                    and not isinstance(w, QtWidgets.QScrollBar):
                return w
            w = w.parentWidget()
        return None

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Wheel:
            field = self.wheel_field(obj)
            if field is not None:
                area = field.parentWidget()
                while area is not None and not isinstance(area, QtWidgets.QAbstractScrollArea):
                    area = area.parentWidget()
                if area is not None:
                    QtWidgets.QApplication.sendEvent(area.verticalScrollBar(), ev)
                return True
        if ev.type() == QtCore.QEvent.Polish and isinstance(obj, QtWidgets.QComboBox) \
                and obj.sizeAdjustPolicy() == QtWidgets.QComboBox.AdjustToContentsOnFirstShow:
            # Don't size dropdowns to their longest option (that made pages wider than the editor);
            # the open list still shows full text.
            obj.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            obj.setMinimumContentsLength(16)
        if ev.type() == QtCore.QEvent.Polish and isinstance(obj, QtWidgets.QAbstractSpinBox):
            if InputPolish.height is None:
                InputPolish.height = QtWidgets.QLineEdit().sizeHint().height()
            obj.lineEdit().setTextMargins(INPUT_INSET, 0, 0, 0)
            obj.setFixedHeight(InputPolish.height)
        return False


# --- help --------------------------------------------------------------------------------------------

def help_html(key):
    text = core.FIELD_HELP.get(key, '')
    paras = [html.escape(p).replace('\n', '<br>') for p in text.split('\n\n') if p.strip()]
    return ''.join(f'<p style="margin:0 0 6px 0">{p}</p>' for p in paras)


class HelpPopup(QtWidgets.QFrame):
    def __init__(self, title, key, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName('HelpPopup')
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        t = QtWidgets.QLabel(title)
        t.setStyleSheet(f'font-weight:700; color:{TEAL};')
        body = QtWidgets.QLabel(help_html(key) or 'No help for this field yet.')
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setFixedWidth(400)
        foot = QtWidgets.QLabel(f'<span style="color:{FAINT}">plan key: {html.escape(key)} · full guide: docs/save-editor.md</span>')
        lay.addWidget(t)
        lay.addWidget(body)
        lay.addWidget(foot)


def show_help(anchor, title, key):
    pop = HelpPopup(title, key, anchor.window())
    pop.adjustSize()
    pos = anchor.mapToGlobal(QtCore.QPoint(anchor.width() + 6, 0))
    screen = (anchor.screen() or QtWidgets.QApplication.primaryScreen()).availableGeometry()
    if pos.x() + pop.width() > screen.right():
        pos.setX(anchor.mapToGlobal(QtCore.QPoint(0, 0)).x() - pop.width() - 6)
    if pos.y() + pop.height() > screen.bottom():
        pos.setY(screen.bottom() - pop.height())
    pop.move(pos)
    pop.show()


class HelpButton(QtWidgets.QToolButton):
    def __init__(self, key, title):
        super().__init__()
        self.setObjectName('Help')
        self.setText('?')
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(f'Help: {title} (or press F1 in the field)')
        self.key, self.title = key, title
        self.clicked.connect(lambda: show_help(self, self.title, self.key))

    def set_help(self, key, title):
        self.key, self.title = key, title
        self.setToolTip(f'Help: {title} (or press F1 in the field)')


def attach_help(widget, key, title, replace=False):
    """Tooltip + F1 help for a field widget and its children. replace: overwrite earlier help tooltips."""
    tip = f'<qt><b>{html.escape(title)}</b>{help_html(key)}</qt>'
    for w in [widget] + widget.findChildren(QtWidgets.QWidget):
        old = w.property('help_key')
        w.setProperty('help_key', key)
        w.setProperty('help_title', title)
        if not w.toolTip() or (replace and old):
            w.setToolTip(tip)


# --- small widgets -----------------------------------------------------------------------------------

BADGE_ROLE = Qt.UserRole + 1     # sidebar rows: colours drawn as a badge right after the name (armor sets)


class KeepColourDelegate(QtWidgets.QStyledItemDelegate):
    """Selected rows keep their own text colour (orange = changed) instead of the plain selection colour.
    Rows with BADGE_ROLE colours get a colour badge right after their name."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        fg = index.data(Qt.ForegroundRole)
        if fg is not None:
            option.palette.setBrush(QtGui.QPalette.HighlightedText, QtGui.QBrush(fg))

    def paint(self, painter, option, index):
        colours = index.data(BADGE_ROLE)
        if not colours:
            return super().paint(painter, option, index)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        text_rect = style.subElementRect(QtWidgets.QStyle.SE_ItemViewItemText, opt, opt.widget)
        gap, inset = 8, 4                       # inset: the style's own text margin
        fm = opt.fontMetrics
        opt.text = fm.elidedText(opt.text, Qt.ElideMiddle, max(0, text_rect.width() - TINT_ICON.width() - gap - inset))
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        x = text_rect.left() + inset + fm.horizontalAdvance(opt.text) + gap
        y = text_rect.center().y() - TINT_ICON.height() // 2 + 1
        tint_icon(colours).paint(painter, QtCore.QRect(x, y, TINT_ICON.width(), TINT_ICON.height()))


class Card(QtWidgets.QFrame):
    """Rounded panel with a title, a help button and a grid of labelled fields."""

    def __init__(self, title, help_key=None, subtitle=None):
        super().__init__()
        self.setObjectName('Card')
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(10)
        head = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel(title)
        t.setObjectName('CardTitle')
        head.addWidget(t)
        if help_key:
            head.addWidget(HelpButton(help_key, title))
        head.addStretch(1)
        self.head = head
        outer.addLayout(head)
        if subtitle:
            s = QtWidgets.QLabel(subtitle)
            s.setObjectName('CardSub')
            s.setWordWrap(True)
            outer.addWidget(s)
        self.grid = QtWidgets.QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(0, LABEL_WIDTH)
        outer.addLayout(self.grid)
        self.body = outer

    def row(self, label, widget, help_key=None, help_title=None, top=None):
        """top: line up the label and help with the widget's first line, this tall, instead of its middle."""
        r = self.grid.rowCount()
        lab = QtWidgets.QLabel(label)
        lab.setObjectName('FieldLabel')
        lab.setFixedWidth(LABEL_WIDTH)              # every card's inputs start at the same x; long labels wrap
        lab.setWordWrap(True)
        valign = Qt.AlignVCenter
        if top:
            lab.setFixedHeight(top)
            valign = Qt.AlignTop
        self.grid.addWidget(lab, r, 0, Qt.AlignLeft | valign)
        if isinstance(widget, QtWidgets.QAbstractSpinBox):
            widget.setMinimumWidth(170)
            self.grid.addWidget(widget, r, 1, Qt.AlignLeft)
        else:
            self.grid.addWidget(widget, r, 1)
        self.last_help = None
        if help_key:
            self.last_help = HelpButton(help_key, help_title or label)
            if top:
                self.last_help.setContentsMargins(0, 0, 0, 0)
                holder = QtWidgets.QWidget()
                hl = QtWidgets.QVBoxLayout(holder)
                hl.setContentsMargins(0, 0, 0, 0)
                holder.setFixedHeight(top)
                hl.addWidget(self.last_help, 0, Qt.AlignVCenter)
                self.grid.addWidget(holder, r, 2, Qt.AlignTop)
            else:
                self.grid.addWidget(self.last_help, r, 2, Qt.AlignVCenter)
            attach_help(widget, help_key, help_title or label)
        return lab

    def full(self, widget):
        self.grid.addWidget(widget, self.grid.rowCount(), 0, 1, 3)


class Segmented(QtWidgets.QWidget):
    changed = Signal(object)

    def __init__(self, options, colours=None):
        """options: [(value, label)]"""
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self.values = []
        for i, (value, label) in enumerate(options):
            b = QtWidgets.QToolButton()
            b.setObjectName('Seg')
            b.setText(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            radius = 'border-top-left-radius:7px;border-bottom-left-radius:7px;' if i == 0 else ''
            if i == len(options) - 1:
                radius += 'border-top-right-radius:7px;border-bottom-right-radius:7px;'
            extra = ''
            if colours:
                extra = f'QToolButton#Seg:checked {{ color: {colours[i]}; border-color: {colours[i]}; }}'
            b.setStyleSheet(f'QToolButton#Seg {{ {radius} }} {extra}')
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.values.append(value)
        lay.addStretch(1)
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))

    def set(self, value):
        for i, v in enumerate(self.values):
            if v == value:
                self.group.button(i).setChecked(True)
                return
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(False)
        self.group.setExclusive(True)

    def value(self):
        i = self.group.checkedId()
        return self.values[i] if i >= 0 else None


class RollField(QtWidgets.QWidget):
    """max / mid / min / custom number, with the game's roll range shown alongside."""
    changed = Signal()

    def __init__(self, decimals=4, step=0.005):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.seg = Segmented([('max', 'Max'), ('mid', 'Mid'), ('min', 'Min'), ('custom', 'Custom')])
        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setRange(0, 1e6)
        self.spin.setSingleStep(step)
        self.spin.setFixedWidth(92)
        self.spin.setKeyboardTracking(False)
        self.range = QtWidgets.QLabel()
        self.range.setObjectName('Muted')
        self.range.setWordWrap(True)
        self.range.setMinimumWidth(70)
        lay.addWidget(self.seg)
        lay.addWidget(self.spin)
        lay.addWidget(self.range, 1)
        self.lo = self.hi = 0
        self.decimals = decimals
        self.seg.changed.connect(self._seg)
        self.spin.valueChanged.connect(self._spin)
        self._quiet = False

    def set_range(self, lo, hi):
        self.lo, self.hi = lo, hi
        fmt = f'{{:,.{2 if self.decimals <= 2 else 3}f}}'
        self.range.setText(f'{fmt.format(lo)} – {fmt.format(hi)}')
        self.range.setToolTip(f'The game rolls {fmt.format(lo)} – {fmt.format(hi)} for this item')
        self._mark()

    def set_value(self, v):
        self._quiet = True
        if v is None or v == 'max':
            self.seg.set('max')
        elif v in ('mid', 'average'):
            self.seg.set('mid')
        elif v == 'min':
            self.seg.set('min')
        else:
            self.seg.set('custom')
            try:
                self.spin.setValue(float(v))
            except (TypeError, ValueError):
                pass
        self.spin.setEnabled(self.seg.value() == 'custom')
        if self.seg.value() != 'custom':
            self.spin.setValue({'max': self.hi, 'mid': (self.lo + self.hi) / 2, 'min': self.lo}[self.seg.value()])
        self._mark()
        self._quiet = False

    def value(self):
        s = self.seg.value()
        if s == 'custom':
            return round(self.spin.value(), self.decimals)
        return s

    def _seg(self, s):
        self.spin.setEnabled(s == 'custom')
        if s != 'custom':
            self._quiet = True
            self.spin.setValue({'max': self.hi, 'mid': (self.lo + self.hi) / 2, 'min': self.lo}[s])
            self._quiet = False
        self._mark()
        self.changed.emit()

    def _spin(self, _):
        self._mark()
        if not self._quiet and self.seg.value() == 'custom':
            self.changed.emit()

    def _mark(self):
        out = self.seg.value() == 'custom' and not (core.f32(self.lo) - 1e-6 <= self.spin.value() <= core.f32(self.hi) + 1e-6)
        if self.spin.property('warn') != out:
            self.spin.setProperty('warn', out)
            self.spin.style().unpolish(self.spin)
            self.spin.style().polish(self.spin)


class OptSpin(QtWidgets.QSpinBox):
    """Integer field that can be left unset (shown as '—')."""

    def __init__(self, lo, hi, unset='—'):
        super().__init__()
        self.setRange(lo - 1, hi)
        self.setSpecialValueText(unset)
        self.setMinimumWidth(90)
        self.setKeyboardTracking(False)
        self.setGroupSeparatorShown(True)

    def opt(self):
        return None if self.value() == self.minimum() else self.value()

    def set_opt(self, v):
        self.blockSignals(True)
        try:
            self.setValue(self.minimum() if v is None else int(v))
        except (TypeError, ValueError):
            self.setValue(self.minimum())
        self.blockSignals(False)


def slider_spin(lo, hi):
    """A slider with a number box, kept in sync. Returns (container, slider, spin)."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    slider = QtWidgets.QSlider(Qt.Horizontal)
    slider.setRange(lo, hi)
    spin = QtWidgets.QSpinBox()
    spin.setRange(lo, hi)
    spin.setKeyboardTracking(False)
    spin.setFixedWidth(80)
    lay.addWidget(slider, 1)
    lay.addWidget(spin)
    slider.valueChanged.connect(spin.setValue)
    spin.valueChanged.connect(slider.setValue)
    return w, slider, spin


class SlotCombo(QtWidgets.QComboBox):
    """Character picker: the field shows a short label, elided with … to fit; the list shows the full
    summary of each character."""
    SHORT = Qt.UserRole + 1

    def paintEvent(self, _):
        p = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(opt)
        short = self.currentData(self.SHORT) or opt.currentText
        room = self.style().subControlRect(QtWidgets.QStyle.CC_ComboBox, opt,
                                           QtWidgets.QStyle.SC_ComboBoxEditField, self).width()
        opt.currentText = self.fontMetrics().elidedText(short, Qt.ElideRight, max(room - 4, 20))
        p.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, opt)
        p.drawControl(QtWidgets.QStyle.CE_ComboBoxLabel, opt)

    def showPopup(self):
        widest = max((self.fontMetrics().horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        self.view().setMinimumWidth(min(widest + 48, 900))
        super().showPopup()


def character_short(slot, char):
    """'Slot 0 · Saboteur · L30 · Hero 39' for the character picker."""
    armor = char['inventory']['armor']
    lvl = armor.get('upgrade_level', 0) + 1
    cls = '-'.join(w.capitalize() for w in core.class_of(char).split('-'))
    hero = f' · Hero {(armor.get("paragon_level") or 0) + 1}' if lvl == core.MAX_LEVEL else ''
    return f'Slot {slot} · {cls} · L{lvl}{hero}'


def combo(items, data=None):
    c = QtWidgets.QComboBox()
    for i, it in enumerate(items):
        c.addItem(it, data[i] if data else it)
    return c


def set_combo(c, value):
    if isinstance(value, int) and not isinstance(value, bool):
        value = int(value)       # ruamel can load a number as its own int type, which findData won't match
    i = c.findData(value)
    c.blockSignals(True)
    if i < 0 and value is not None:
        c.addItem(f'{value} (unknown)', value)
        i = c.count() - 1
    c.setCurrentIndex(max(i, 0))
    c.blockSignals(False)


def discard(w):
    """Remove a widget from its layout right away (deleteLater alone leaves it on screen until idle)."""
    w.hide()
    w.setParent(None)
    w.deleteLater()


GUIDE_HTML = (
    '<ul style="margin-left:-20px">'
    '<li><b>Savegame ▸ Open</b> a savegame folder. Pick a character under <b>CHARACTER</b>; its whole '
    'inventory is listed to edit in place. Change an item, <b>Delete</b> it, or use <b>＋ Add</b> next to '
    'Weapons, Equipment or Armor sets for a new one. New and changed items show in orange; ★ marks equipped ones. <b>Profile</b> has levels, keys and resources.</li>'
    '<li>Switching character keeps your edits; characters with unsaved edits show ● in the dropdown. '
    '<b>Savegame ▸ Save</b> writes all of them into an edited copy of the savegame, in a folder you choose. '
    'It is disabled while the Checks tab shows problems.</li>'
    '<li><b>Recipe ▸ Apply recipe</b> adds a saved set of items and profile values to the character (try the '
    'examples). <b>Recipe ▸ Save as recipe</b> saves some of this character\'s items as a recipe for later.</li>'
    '<li>Every field has a <b>?</b> button; press <b>F1</b> in a field for the same help.</li>'
    '<li><b>Changes</b> shows what you changed (to see the whole working copy as YAML, turn on the YAML tab in Settings).</li>'
    '<li>Values the game never generates are refused unless <b>Allow untested values</b> is on '
    '(<b>Settings</b> tab, right).</li></ul>')


def display_path(p):
    """Paths inside the project are shown relative to it."""
    rel = os.path.relpath(os.path.abspath(p), ROOT)
    return p if rel.startswith('..') else rel


def hline():
    f = QtWidgets.QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f'background:{BORDER};')
    return f


# --- YAML document (comment-preserving) ---------------------------------------------------------------

def make_yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def align_socket_lists(text):
    """Re-align 'main:    [...]' under 'branch1: [...]' the way the hand-written plans do."""
    lines = text.split('\n')
    pat = re.compile(r'^(\s*)(main|branch1|branch2):\s*(\[.*)$')
    i = 0
    while i < len(lines):
        m = pat.match(lines[i])
        if not m:
            i += 1
            continue
        j = i
        group = []
        while j < len(lines):
            mm = pat.match(lines[j])
            if not mm or mm.group(1) != m.group(1):
                break
            group.append(mm)
            j += 1
        if any(g.group(2) != 'main' for g in group):
            for k, g in enumerate(group):
                lines[i + k] = f'{g.group(1)}{(g.group(2) + ":").ljust(9)}{g.group(3)}'
        i = j
    return '\n'.join(lines)


def strip_comments(node):
    """Drop the comments (and blank lines, which ruamel keeps as comments) carried by a copied entry,
    so an item from a recipe reads like the savegame's own entries."""
    if isinstance(node, (CommentedMap, CommentedSeq)):
        node.ca.items.clear()
        node.ca.comment = None
        node.ca.end = None
        for v in (node.values() if isinstance(node, CommentedMap) else node):
            strip_comments(v)
    return node


def flow_seq(items):
    s = CommentedSeq(items)
    s.fa.set_flow_style()
    return s


def flow_map(pairs):
    m = CommentedMap(pairs)
    m.fa.set_flow_style()
    return m


KEY_ORDER = {
    'root': core.SECTIONS,
    'weapons': ['replace', 'code', 'rarity', 'level', 'damage', 'stats', 'sockets', 'perk', 'locked', 'new',
                'tint', 'equip'],
    'equipment': ['replace', 'code', 'rarity', 'level', 'damage', 'sockets', 'perk', 'locked', 'new', 'tint',
                  'equip'],
    'armor_sets': ['replace', 'rarity', 'level', 'colors', 'effects', 'locked', 'new', 'equip'],
    'perk': ['cause', 'effect', 'efficiency', 'value'],
    'stats': ['fire_rate', 'charge_time', 'clip_size', 'critical_hit_chance'],
    'sockets': ['main', 'branch1', 'branch2'],
    'profile': ['level', 'hero_level', 'keys', 'cores', 'metals', 'credits', 'flowers'],
    'remove': ['weapons', 'equipment', 'armor_sets'],
    'colors': core.ARMOR_AREAS_MENU,
    'armor_area': list(core.ARMOR_AREA_KEYS),
    'replace': ['index', 'code'],
}


def set_key(m, key, value, order=()):
    """Set m[key], inserting a new key at its natural position so files stay readable."""
    if key in m:
        m[key] = value
        return
    pos = len(m)
    if key in order:
        later = set(order[order.index(key) + 1:])
        for i, k in enumerate(m):
            if k in later:
                pos = i
                break
    m.insert(pos, key, value)


def del_key(m, key):
    if isinstance(m, dict) and key in m:
        del m[key]


def child_map(m, key, order=(), flow=False):
    v = m.get(key)
    if not isinstance(v, dict):
        v = flow_map([]) if flow else CommentedMap()
        set_key(m, key, v, order)
    return v


class PlanDoc:
    def __init__(self, path=None, text=None):
        self.path = path
        self.pending_name = None        # name chosen before the first save (pre-fills Save as)
        self.yaml = make_yaml()
        if text is None and path:
            with open(path) as f:
                text = f.read()
        self.data = self.parse(text or '')
        self.saved_text = self.text() if path else ''     # what is on disk; '' = never saved

    def parse(self, text):
        data = self.yaml.load(text) if text.strip() else None
        if data is None:
            data = CommentedMap()
        if not isinstance(data, CommentedMap):
            raise core.PlanError('a plan must be a mapping with weapons / equipment / armor_sets / profile')
        return data

    @property
    def name(self):
        return os.path.basename(self.path) if self.path else (self.pending_name or 'untitled.yaml')

    def text(self):
        s = io.StringIO()
        self.yaml.dump(self.data, s)
        return align_socket_lists(s.getvalue()) if self.data else ''

    def entries(self, section, create=False):
        v = self.data.get(section)
        if isinstance(v, dict):                       # a single entry written as a mapping
            v = CommentedSeq([v])
            self.data[section] = v
        if not isinstance(v, list):
            if not create:
                return []
            v = CommentedSeq()
            set_key(self.data, section, v, KEY_ORDER['root'])
        return v

    def section_map(self, section, create=False):
        v = self.data.get(section)
        if not isinstance(v, dict):
            if not create:
                return None
            v = CommentedMap()
            set_key(self.data, section, v, KEY_ORDER['root'])
        return v

    def prune(self):
        """Drop empty sections so the file only holds what the plan changes."""
        for k in list(self.data):
            v = self.data[k]
            if k in ('profile', 'remove'):
                for kk in list(v or {}):
                    if v[kk] in (None, {}, []):
                        del v[kk]
            if v in (None, {}, []):
                del self.data[k]


# --- entry templates ------------------------------------------------------------------------------

def new_weapon(code='smg'):
    m = CommentedMap([('code', code), ('rarity', 'legendary'), ('level', 30), ('damage', 'max')])
    set_key(m, 'new', True, KEY_ORDER['weapons'])   # the gear menu's "new" marker, like a fresh pickup
    return m


def new_equipment():
    return CommentedMap([('code', 'grenade'), ('rarity', 'legendary'), ('level', 30), ('damage', 'max')])


def new_armor_set():
    return CommentedMap([('rarity', 1), ('level', 30),
                         ('effects', CommentedMap([('movement_speed', 1.05), ('rush_recharge', 1.1)])),
                         ('locked', True)])


# --- socket tree -------------------------------------------------------------------------------------

def socket_string(stype, corev):
    colour = core.SOCKET_NAMES[stype]
    if corev is None:
        return colour
    return f'{colour} {core.CORE_NAMES[corev[0]]}{corev[1]}'


def parse_socket_safe(spec):
    try:
        return core.parse_socket(spec, 'socket')
    except core.PlanError:
        return None


class SocketTree(QtWidgets.QWidget):
    """Clickable upgrade tree. groups: {'main': [...], 'branch1': [...], 'branch2': [...]} of socket specs."""
    changed = Signal()

    S, R = 64, 19

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.groups = {'main': [], 'branch1': [], 'branch2': []}
        self.rarity = 4
        self.perk = False
        self.hover = None
        self.setMouseTracking(True)
        if kind == 'weapon':
            self.setMinimumSize(500, 236)
        else:
            self.setMinimumSize(560, 104)

    def set_data(self, groups, rarity, perk):
        self.groups = {k: list(groups.get(k) or []) for k in ('main', 'branch1', 'branch2')}
        self.rarity = rarity if isinstance(rarity, int) and 0 <= rarity <= 4 else 4
        self.perk = perk
        self.update()

    def capacity(self, g):
        if self.kind == 'equipment':
            return 6 if g == 'main' else 0
        return {'main': 5, 'branch1': 3, 'branch2': 4}[g]

    def game_size(self, g):
        if self.kind == 'equipment':
            return core.EQUIPMENT_TREE[self.rarity][0] if g == 'main' else 0
        tm, tb1, tb2, _ = core.WEAPON_TREE[self.rarity]
        return {'main': tm, 'branch1': tb1, 'branch2': tb2}[g]

    def pos(self, g, i):
        S = self.S
        x0 = 40 + max(0, (self.width() - (520 if self.kind == 'weapon' else 560)) / 2)
        if self.kind == 'equipment':
            return QtCore.QPointF(x0 + i * S, 52)
        if g == 'main':
            return QtCore.QPointF(x0 + i * S, 118)
        if g == 'branch1':
            return QtCore.QPointF(x0 + (i + 0.5) * S, 42)
        if g == 'branch2':
            return QtCore.QPointF(x0 + (i + 1.5) * S, 194)
        return QtCore.QPointF(x0 + 3.5 * S, 42)            # perk

    def parent_pos(self, g, i):
        if g == 'main':
            return self.pos('main', i - 1) if i else None
        if g == 'branch1':
            return self.pos('branch1', i - 1) if i else self.pos('main', 0)
        if g == 'branch2':
            return self.pos('branch2', i - 1) if i else self.pos('main', 1)

    def parent_spec(self, g, i):
        if g == 'main':
            return self.groups['main'][i - 1] if i else None
        if i:
            return self.groups[g][i - 1]
        root = 0 if g == 'branch1' else 1
        return self.groups['main'][root] if len(self.groups['main']) > root else None

    def nodes(self):
        out = []
        for g in ('main', 'branch1', 'branch2'):
            for i, spec in enumerate(self.groups[g]):
                out.append(('socket', g, i, spec))
            n = len(self.groups[g])
            can = n < self.capacity(g)
            if g == 'branch1' and not self.groups['main']:
                can = False
            if g == 'branch2' and len(self.groups['main']) < 2:
                can = False
            if can:
                out.append(('add', g, n, None))
        return out

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        R = self.R
        if self.kind == 'weapon':
            p.setPen(QtGui.QColor(FAINT))
            f = p.font()
            f.setPixelSize(10)
            f.setBold(True)
            p.setFont(f)
            x0 = self.pos('main', 0).x()
            p.drawText(QtCore.QPointF(x0 + 4.15 * self.S, 46), 'BRANCH 1')
            p.drawText(QtCore.QPointF(x0 + 4.7 * self.S, 122), 'MAIN')
            p.drawText(QtCore.QPointF(x0 + 5.05 * self.S, 198), 'BRANCH 2')
        # links
        for kind, g, i, spec in self.nodes():
            a = self.parent_pos(g, i)
            if a is None:
                continue
            b = self.pos(g, i)
            if kind == 'add':
                p.setPen(QtGui.QPen(QtGui.QColor(BORDER), 2, Qt.DashLine))
            else:
                ps, cs = parse_socket_safe(self.parent_spec(g, i)), parse_socket_safe(spec)
                if ps and cs and ps[0] == cs[0] and cs[0] in ('core1', 'core2', 'core3'):
                    col = QtGui.QColor(SOCKET_COLOURS[cs[0]])
                    glow = QtGui.QColor(col)
                    glow.setAlpha(60)
                    p.setPen(QtGui.QPen(glow, 12, Qt.SolidLine, Qt.RoundCap))
                    p.drawLine(a, b)
                    p.setPen(QtGui.QPen(col, 4, Qt.SolidLine, Qt.RoundCap))
                else:
                    p.setPen(QtGui.QPen(QtGui.QColor('#3a4556'), 3))
            p.drawLine(a, b)
        # perk node
        if self.kind == 'weapon':
            b1 = self.groups['branch1']
            pp = self.pos('perk', 0)
            if b1:
                p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if self.perk else BORDER), 3 if self.perk else 2,
                                    Qt.SolidLine if self.perk else Qt.DashLine))
                p.drawLine(self.pos('branch1', len(b1) - 1), pp)
            self._diamond(p, pp, self.perk)
        elif self.perk:
            n = len(self.groups['main'])
            pp = self.pos('main', 6) + QtCore.QPointF(self.S * 0.3, 0)
            if n:
                p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2, Qt.DotLine))
                p.drawLine(self.pos('main', n - 1) + QtCore.QPointF(self.R, 0), pp)
            self._diamond(p, pp, True)
        # sockets
        for kind, g, i, spec in self.nodes():
            c = self.pos(g, i)
            hovered = self.hover == (g, i)
            beyond = i >= self.game_size(g)
            if kind == 'add':
                p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if hovered else '#465266'), 2, Qt.DashLine))
                p.setBrush(QtGui.QColor(CARD_HI if hovered else CARD))
                p.drawEllipse(c, R - 4, R - 4)
                p.setPen(QtGui.QColor(ACCENT if hovered else MUTED))
                f = p.font()
                f.setPixelSize(20)
                f.setBold(False)
                p.setFont(f)
                p.drawText(QtCore.QRectF(c.x() - R, c.y() - R - 1, 2 * R, 2 * R), Qt.AlignCenter, '+')
                continue
            parsed = parse_socket_safe(spec)
            if beyond:
                p.setPen(QtGui.QPen(QtGui.QColor(LEVEL_COLOURS['untested']), 1.5, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, R + 6, R + 6)
            if hovered:
                halo = QtGui.QColor(TEXT)
                halo.setAlpha(40)
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(c, R + 5, R + 5)
            if parsed is None:
                p.setPen(QtGui.QPen(QtGui.QColor(LEVEL_COLOURS['error']), 3))
                p.setBrush(QtGui.QColor(BG))
                p.drawEllipse(c, R, R)
                p.drawText(QtCore.QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R), Qt.AlignCenter, '?')
                continue
            stype, corev = parsed
            p.setPen(QtGui.QPen(QtGui.QColor(SOCKET_COLOURS[stype]), 4))
            p.setBrush(QtGui.QColor('#0b0e13'))
            p.drawEllipse(c, R, R)
            if corev:
                ctype, lvl = corev
                if ctype == 4:
                    g2 = QtGui.QConicalGradient(c, 90)
                    for k, col in enumerate(['#ff6b6b', '#ffd23c', '#4ade80', '#3b8cff', '#c084fc', '#ff6b6b']):
                        g2.setColorAt(k / 5, QtGui.QColor(col))
                    p.setBrush(QtGui.QBrush(g2))
                else:
                    rg = QtGui.QRadialGradient(c - QtCore.QPointF(4, 4), R)
                    base = QtGui.QColor(CORE_COLOURS[ctype])
                    rg.setColorAt(0, base.lighter(140))
                    rg.setColorAt(1, base.darker(130))
                    p.setBrush(QtGui.QBrush(rg))
                p.setPen(Qt.NoPen)
                p.drawEllipse(c, R - 7, R - 7)
                f = p.font()
                f.setPixelSize(13)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QtGui.QColor('#0b0e13'))
                p.drawText(QtCore.QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R), Qt.AlignCenter, str(lvl))
        p.end()

    def _diamond(self, p, c, on):
        d = 13
        poly = QtGui.QPolygonF([c + QtCore.QPointF(0, -d), c + QtCore.QPointF(d, 0),
                                c + QtCore.QPointF(0, d), c + QtCore.QPointF(-d, 0)])
        p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if on else '#465266'), 2, Qt.SolidLine if on else Qt.DashLine))
        p.setBrush(QtGui.QColor(ACCENT if on else CARD))
        p.drawPolygon(poly)

    def hit(self, pt):
        for kind, g, i, spec in self.nodes():
            if QtCore.QLineF(pt, self.pos(g, i)).length() <= self.R + 3:
                return kind, g, i
        return None

    def mouseMoveEvent(self, e):
        h = self.hit(e.position())
        new = (h[1], h[2]) if h else None
        if new != self.hover:
            self.hover = new
            self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            self.update()
        if h and h[0] == 'socket':
            spec = self.groups[h[1]][h[2]]
            beyond = h[2] >= self.game_size(h[1])
            tip = f'{h[1]} socket {h[2] + 1}: {spec}'
            if beyond:
                tip += f'\nBeyond what game-made {core.RARITIES[self.rarity]} items have (untested)'
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), tip + '\nClick to change', self)
        elif h:
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), f'Add a {h[1]} socket', self)
        else:
            QtWidgets.QToolTip.hideText()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        h = self.hit(e.position())
        if not h:
            return
        kind, g, i = h
        if kind == 'add':
            prev = self.groups[g][-1] if self.groups[g] else (self.groups['main'][-1] if self.groups['main'] else None)
            parsed = parse_socket_safe(prev) if prev else None
            stype = parsed[0] if parsed else 'core2'
            self.groups[g].append(socket_string(stype, (core.SOCKET_DEFAULT_CORE[stype], 6)))
            self.changed.emit()
            self.update()
            return
        self.socket_menu(g, i, e.globalPosition().toPoint())

    def socket_menu(self, g, i, where):
        parsed = parse_socket_safe(self.groups[g][i]) or ('core2', None)
        stype, corev = parsed
        menu = QtWidgets.QMenu(self)
        head = menu.addAction('Socket colour')
        head.setEnabled(False)
        for name, t in core.SOCKETS.items():
            a = menu.addAction(dot_icon(SOCKET_COLOURS[t], 14), f'{name.capitalize()}  ·  '
                               + {'core1': 'Boost', 'core2': 'Power', 'core3': 'Utility', 'core': 'any'}[t])
            a.setCheckable(True)
            a.setChecked(t == stype)
            a.triggered.connect(lambda _=False, t=t: self._set(g, i, t, (core.SOCKET_DEFAULT_CORE[t], corev[1])
                                                               if corev and corev[0] == core.SOCKET_DEFAULT_CORE[stype]
                                                               else corev))
        menu.addSeparator()
        head = menu.addAction('Core')
        head.setEnabled(False)
        match = core.SOCKET_DEFAULT_CORE[stype]
        a = menu.addAction(dot_icon(CORE_COLOURS[match], 14), f'Matching level-6 core ({core.CORE_NAMES[match]})')
        a.triggered.connect(lambda: self._set(g, i, stype, (match, 6)))
        for name, t in core.CORES.items():
            sub = menu.addMenu(dot_icon(CORE_COLOURS[t], 14), name.capitalize())
            for lvl in range(1, 7):
                a = sub.addAction(f'Level {lvl}')
                a.setCheckable(True)
                a.setChecked(corev == (t, lvl))
                a.triggered.connect(lambda _=False, t=t, lvl=lvl: self._set(g, i, stype, (t, lvl)))
        a = menu.addAction('Empty socket')
        a.setCheckable(True)
        a.setChecked(corev is None)
        a.triggered.connect(lambda: self._set(g, i, stype, None))
        menu.addSeparator()
        a = menu.addAction('Remove socket')
        a.triggered.connect(lambda: self._remove(g, i))
        menu.exec(where)

    def _set(self, g, i, stype, corev):
        self.groups[g][i] = socket_string(stype, corev)
        self.changed.emit()
        self.update()

    def _remove(self, g, i):
        del self.groups[g][i]
        if g == 'main' and not self.groups['main']:
            self.groups['branch1'] = []
        if g == 'main' and len(self.groups['main']) < 2:
            self.groups['branch2'] = []
        self.changed.emit()
        self.update()

    def clear(self):
        self.groups = {'main': [], 'branch1': [], 'branch2': []}
        self.changed.emit()
        self.update()


# --- editors -----------------------------------------------------------------------------------------

class Editor(QtWidgets.QWidget):
    """Base for the pages on the right. Widgets write straight into the bound ruamel mapping."""
    changed = Signal()

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.m = None
        self.loading = False
        self.lay = QtWidgets.QVBoxLayout(self)
        self.lay.setContentsMargins(20, 18, 20, 24)
        self.lay.setSpacing(16)

    def header(self, title, sub=''):
        box = QtWidgets.QVBoxLayout()
        box.setSpacing(2)
        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName('PageTitle')
        self.sub = QtWidgets.QLabel(sub)
        self.sub.setObjectName('PageSub')
        self.sub.setWordWrap(True)
        self.sub.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)   # wrap, don't push
        self.sub.setMinimumWidth(120)
        box.addWidget(self.title)
        box.addWidget(self.sub)
        row = QtWidgets.QHBoxLayout()
        row.addLayout(box, 1)
        self.header_actions = QtWidgets.QHBoxLayout()
        self.header_actions.setSpacing(8)
        row.addLayout(self.header_actions)
        self.lay.addLayout(row)

    def entry_actions(self):
        """The Duplicate and Delete buttons on weapon / equipment / armor-set pages."""
        dup = QtWidgets.QPushButton('Duplicate')
        dup.setToolTip('Add a copy of this item as a new item (Ctrl+D)')
        dup.clicked.connect(self.main.duplicate)
        self.header_actions.addWidget(dup)
        self.del_btn = QtWidgets.QPushButton('Delete')
        self.del_btn.setObjectName('Danger')
        self.del_btn.clicked.connect(lambda: self.main.delete_entry(self.ctx))
        self.header_actions.addWidget(self.del_btn)

    def update_entry_actions(self):
        if hasattr(self, 'del_btn') and self.m is not None:
            owned = self.m.get('replace') is not None
            equipped = bool(self.m.get('equip'))
            self.del_btn.setEnabled(not equipped)
            self.del_btn.setToolTip(equipped_delete_hint(self.ctx[0], self.m) if equipped else
                                    'Delete this item from the savegame (when the savegame is saved). ⌘Z undoes '
                                    'it.' if owned else 'Remove this new item')

    def bind(self, m, *ctx):
        self.m = m
        self.ctx = ctx
        self.loading = True
        try:
            self.load()
        finally:
            self.loading = False

    def commit(self):
        if not self.loading and self.m is not None:
            self.changed.emit()

    def load(self):
        pass

    def on(self, signal, fn):
        def handler(*a):
            if self.loading or self.m is None:
                return
            fn(*a)
            self.after_edit()
            self.commit()
        signal.connect(handler)

    def after_edit(self):
        pass


def short_armor_name(label):
    """'armor set, looted, 2 effects' → 'Looted set': the sidebar shows the set's colours instead."""
    m = re.match(r'armor set, ([^,]+)', label)
    return f'{m.group(1).capitalize()} set' if m else label


def armor_colours(spec):
    """The set's four colours in the gear menu's order (plates, suit, visor, accent); grey where unset."""
    cols = spec.get('colors') if isinstance(spec, dict) and isinstance(spec.get('colors'), dict) else {}
    out = []
    for area in core.ARMOR_AREAS_MENU:
        v = cols.get(area)
        v = v.get('color') if isinstance(v, dict) else v
        try:
            out.append(floats_to_hex(core.parse_colour(v, area)[:3]) if v is not None else FAINT)
        except (core.PlanError, TypeError, ValueError):
            out.append(FAINT)
    return out


def equipped_delete_hint(section, e):
    """Why an equipped item can't be deleted (its slot can't be left empty), in plain words."""
    if section == 'armor_sets':
        return 'You\'re wearing this armor set. Wear another one first, then delete this one.'
    slot = equip_slot(section, e)
    what = f'{slot} weapon' if section == 'weapons' and slot else 'item in the equipment slot'
    return f'This is your equipped {what}. Equip another one first, then delete this one.'


def equip_slot(section, e):
    """The slot an entry fills when equipped: its weapon category, or the section's single slot."""
    return core.WEAPON_CATEGORY.get(e.get('code')) if section == 'weapons' else section


class EntryFlags:
    """equip / locked / new rows (added to the entry's first card) and, for weapons and equipment, a Tint
    card with the tint. Shared by every entry kind. Which owned item an entry rebuilds (replace:)
    is implicit: it comes from opening a savegame."""

    def __init__(self, editor, section, card):
        self.editor, self.section = editor, section
        self.equip = QtWidgets.QCheckBox('Wear it' if section == 'armor_sets' else 'Equip it')
        eq = QtWidgets.QWidget()
        el = QtWidgets.QHBoxLayout(eq)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(8)
        self.star = QtWidgets.QLabel('★')              # the same mark equipped items get in the sidebar
        self.star.setToolTip('Equipped items are marked ★ in the list')
        el.addWidget(self.equip)
        el.addWidget(self.star)
        el.addStretch(1)
        card.row('Equip', eq, 'entry.equip')
        attach_help(self.equip, 'entry.equip', 'Equip')
        flags = QtWidgets.QWidget()
        fl = QtWidgets.QHBoxLayout(flags)
        fl.setContentsMargins(0, 0, 0, 0)
        self.locked = QtWidgets.QCheckBox('Locked')
        self.new = QtWidgets.QCheckBox('Marked new')
        fl.addWidget(self.locked)
        fl.addSpacing(8)
        fl.addWidget(HelpButton('entry.locked', 'Locked'))
        fl.addSpacing(24)
        fl.addWidget(self.new)
        fl.addSpacing(8)
        fl.addWidget(HelpButton('entry.new', 'Marked new'))
        fl.addStretch(1)
        attach_help(self.locked, 'entry.locked', 'Locked')
        attach_help(self.new, 'entry.new', 'Marked new')
        card.row('Flags', flags)
        self.tint = self.card = None
        if section != 'armor_sets':
            sub = ('The colour tint the item is drawn with. Each swatch shows the game\'s three colours for that '
                   'tint at the item\'s rarity.')
            if section == 'equipment':
                sub += ' Equipment only shows it in the gear menu\'s preview.'
            self.card = Card('Tint', subtitle=sub)
            self.tint = QtWidgets.QComboBox()
            self.tint.setIconSize(TINT_ICON)
            self.tint.addItem(tint_icon(), 'Random', None)  # relabelled "Keep current tint" for replaced items in load
            for t in range(10):
                self.tint.addItem(f'Tint {t}', t)
            self.tint_rarity = None
            self.paint_tints(4)
            self.card.row('Tint', self.tint, 'entry.tint')
        e = editor
        self.equip.toggled.connect(self._star)
        e.on(self.equip.toggled, lambda _: self._equip())
        e.on(self.locked.toggled, lambda v: self._set('locked', True if v else None))
        e.on(self.new.toggled, lambda v: self._set('new', True if v else None))
        if self.tint:
            e.on(self.tint.currentIndexChanged, lambda _: self._tint())

    def _set(self, key, value):
        m = self.editor.m
        if value is None:
            del_key(m, key)
        else:
            set_key(m, key, value, KEY_ORDER[self.section])

    def _star(self, on):
        self.star.setStyleSheet(f'color: {TEXT if on else FAINT};')

    def _equip(self):
        if not self.equip.isChecked():
            self._set('equip', None)
            self.give_back()
            return
        if not self.editor.m.get('equip'):
            self._set('equip', True)
        self.claim_slot()

    def give_back(self):
        """This entry left its slot (unequipped, or a weapon changed type): re-equip the entries it pushed
        out, as long as nothing else holds their slot, so the sidebar matches what the save will have."""
        me = self.editor.m
        entries = self.editor.main.doc.entries(self.section)
        for e, was in self.editor.main.freed_by.pop(id(me), []):
            if not any(x is e for x in entries):
                continue
            slot = self.slot_of(e)
            if any(isinstance(x, dict) and x.get('equip') and self.slot_of(x) == slot for x in entries):
                continue
            set_key(e, 'equip', was, KEY_ORDER[self.section])

    def slot_of(self, e):
        return equip_slot(self.section, e)

    def claim_slot(self):
        """Equipping this entry unequips whichever other entry held the same slot (each slot holds one)."""
        me = self.editor.m
        if not me.get('equip'):
            return []
        slot = self.slot_of(me)
        freed = []
        for i, e in enumerate(self.editor.main.doc.entries(self.section)):
            if e is not me and isinstance(e, dict) and e.get('equip') and self.slot_of(e) == slot:
                self.editor.main.freed_by.setdefault(id(me), []).append((e, e.get('equip')))
                del_key(e, 'equip')
                freed.append(core.entry_label(self.section, e, ITEM_NAMES))
        if freed:
            why = {'equipment': 'the equipment slot holds one item',
                   'armor_sets': 'only one armor set is worn at a time'}.get(slot, f'the {slot} slot holds one weapon')
            self.editor.main.flash(f'Unequipped {", ".join(freed)}: {why}')
        return freed

    def _tint(self):
        self._set('tint', self.tint.currentData())

    def paint_tints(self, rarity):
        """Show each tint's colours for this rarity (every rarity has its own 10)."""
        if not self.tint or rarity == self.tint_rarity:
            return
        self.tint_rarity = rarity
        for t in range(10):
            colours = core.tint_hex(rarity, t)
            self.tint.setItemIcon(t + 1, tint_icon(colours))
            self.tint.setItemData(t + 1, f'{core.RARITIES[rarity].capitalize()} tint {t}: '
                                  + ', '.join(colours), Qt.ToolTipRole)

    def load(self, m):
        self.equip.setChecked(bool(m.get('equip')))
        self._star(self.equip.isChecked())
        self.locked.setChecked(bool(m.get('locked')))
        self.new.setChecked(bool(m.get('new')))
        if self.tint:
            self.tint.setItemText(0, 'Keep current tint' if m.get('replace') is not None else 'Random')
            t = m.get('tint')
            set_combo(self.tint, t if isinstance(t, int) else None)


class ItemEditor(Editor):
    """Weapons and equipment."""

    def __init__(self, main, section):
        super().__init__(main)
        self.section = section
        self.weapon = section == 'weapons'
        kind = 'weapon' if self.weapon else 'equipment'
        self.header('Weapon' if self.weapon else 'Equipment')
        self.entry_actions()

        basics = Card('Item', subtitle='Type, rarity and level decide every range below.')
        self.code = QtWidgets.QComboBox()
        if self.weapon:
            for slot in ('primary', 'secondary', 'heavy'):
                self.code.addItem(f'— {slot.upper()} —', None)
                self.code.model().item(self.code.count() - 1).setEnabled(False)
                for c, cat in core.WEAPON_CATEGORY.items():
                    if cat == slot:
                        extra = f' · {PRIMARY_CLASS[c]}' if c in PRIMARY_CLASS else ''
                        extra += ' · add-on' if c in core.DLC_ITEMS else ''
                        self.code.addItem(f'{WEAPON_NAMES[c]}   ({c}{extra})', c)
        else:
            for c in core.EQUIPMENT:
                self.code.addItem(f'{EQUIPMENT_NAMES[c]}   ({c}{" · add-on" if c in core.DLC_ITEMS else ""})', c)
        basics.row('Type', self.code, f'{kind}.code')
        self.rarity = Segmented([(r, r.capitalize()) for r in core.RARITIES], RARITY_COLOURS)
        basics.row('Rarity', self.rarity, f'{kind}.rarity')
        lv, self.level_slider, self.level = slider_spin(1, core.MAX_LEVEL)
        basics.row('Level', lv, f'{kind}.level')
        self.flags = EntryFlags(self, section, basics)
        self.lay.addWidget(basics)

        stats = Card('Damage and stats', subtitle='Pick a point in the range the game rolls, or type your own '
                                                  '(outside the range needs "allow untested").')
        self.damage = RollField(decimals=2, step=10)
        stats.row('Damage', self.damage, f'{kind}.damage')
        self.stats = {}             # 'rate' is fire_rate or charge_time, whichever the weapon has
        self.rate_label = None
        if self.weapon:
            for s in ('rate', 'clip_size', 'critical_hit_chance'):
                f = RollField()
                lab = stats.row(STAT_TITLES.get(s, 'Fire rate'), f, f'weapon.stats.{"fire_rate" if s == "rate" else s}',
                                STAT_TITLES.get(s, 'Fire rate'))
                if s == 'rate':
                    self.rate_label, self.rate_help = lab, stats.last_help
                self.stats[s] = f
        self.lay.addWidget(stats)

        sockets = Card('Sockets and cores', f'{kind}.sockets',
                       'Click a socket to change its colour or core; click + to add one. Same-colour neighbours '
                       'link up (synergy). Dotted pink rings are beyond what game-made items of this rarity have.')
        self.tree = SocketTree(kind)
        sockets.full(self.tree)
        tools = QtWidgets.QHBoxLayout()
        clear = QtWidgets.QPushButton('Clear')
        clear.setToolTip('Remove every socket')
        clear.clicked.connect(self.tree.clear)
        tools.addWidget(clear)
        tools.addStretch(1)
        sockets.body.addLayout(tools)
        self.lay.addWidget(sockets)

        if self.weapon:
            perk = Card('Perk', 'weapon.perk', 'A conditional action at the end of branch 1.')
            self.perk_on = QtWidgets.QCheckBox('This weapon has a perk')
            perk.full(self.perk_on)
            attach_help(self.perk_on, 'weapon.perk', 'Perk')
            self.cause = QtWidgets.QComboBox()
            for c in core.CAUSES:
                self.cause.addItem(f'{c}   ·   {core.CAUSE_TEXT[c]}{"" if c in core.CAUSES_SEEN else "   (untested)"}', c)
                if c not in core.CAUSES_SEEN:
                    self.cause.setItemData(self.cause.count() - 1, QtGui.QColor(LEVEL_COLOURS['untested']), Qt.ForegroundRole)
            perk.row('Cause', self.cause, 'weapon.perk.cause')
            self.effect = QtWidgets.QComboBox()
            for c in core.EFFECTS:
                self.effect.addItem(f'{c}   ·   {core.EFFECT_TEXT[c]}{"" if c in core.EFFECTS_SEEN else "   (untested)"}', c)
                if c not in core.EFFECTS_SEEN:
                    self.effect.setItemData(self.effect.count() - 1, QtGui.QColor(LEVEL_COLOURS['untested']), Qt.ForegroundRole)
            perk.row('Effect', self.effect, 'weapon.perk.effect')
            ew = QtWidgets.QWidget()
            el = QtWidgets.QHBoxLayout(ew)
            el.setContentsMargins(0, 0, 0, 0)
            self.eff_slider = QtWidgets.QSlider(Qt.Horizontal)
            self.eff_slider.setRange(50, 100)
            self.eff = QtWidgets.QDoubleSpinBox()
            self.eff.setRange(0, 10)
            self.eff.setDecimals(2)
            self.eff.setSingleStep(0.05)
            self.eff.setKeyboardTracking(False)
            self.eff.setFixedWidth(80)
            el.addWidget(self.eff_slider, 1)
            el.addWidget(self.eff)
            self.eff_slider.valueChanged.connect(lambda v: self.eff.setValue(v / 100))
            self.eff.valueChanged.connect(lambda v: (self.eff_slider.blockSignals(True),
                                                     self.eff_slider.setValue(int(round(min(max(v, .5), 1) * 100))),
                                                     self.eff_slider.blockSignals(False)))
            perk.row('Efficiency', ew, 'weapon.perk.efficiency')
            vw = QtWidgets.QWidget()
            vl = QtWidgets.QHBoxLayout(vw)
            vl.setContentsMargins(0, 0, 0, 0)
            self.value_default = QtWidgets.QCheckBox('Game default')
            self.value = QtWidgets.QDoubleSpinBox()
            self.value.setRange(0, 100)
            self.value.setDecimals(4)
            self.value.setSingleStep(0.05)
            self.value.setKeyboardTracking(False)
            self.value_hint = QtWidgets.QLabel()
            self.value_hint.setWordWrap(True)
            self.value_hint.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            self.value_hint.setObjectName('Muted')
            presets = QtWidgets.QToolButton()
            presets.setText('Presets ▾')
            presets.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            pm = QtWidgets.QMenu(presets)
            for v, label in ((0.5, '0.5 → 25% on enemy hit'), (1.0, '1.0 → 50% on enemy hit'),
                             (2.0, '2.0 → every enemy hit (100%)')):
                a = pm.addAction(label)
                a.triggered.connect(lambda _=False, v=v: (self.value_default.setChecked(False), self.value.setValue(v)))
            presets.setMenu(pm)
            vl.addWidget(self.value_default)
            vl.addWidget(self.value)
            vl.addWidget(presets)
            vl.addWidget(self.value_hint, 1)
            perk.row('Trigger value', vw, 'weapon.perk.value')
            self.perk_summary = QtWidgets.QLabel()
            self.perk_summary.setObjectName('Derived')
            self.perk_summary.setWordWrap(True)
            perk.full(self.perk_summary)
            self.lay.addWidget(perk)
        else:
            perk = Card('Perks', 'equipment.perk', 'Attribute perks after the 5th socket (legendary only).')
            self.eq_perks = {}
            for p, desc in (('fast_recharge', 'doubles how fast it refills'),
                            ('speed_jolt', 'speed boost when thrown'),
                            ('double_reserve', 'carry twice as many (never rolled, untested)')):
                cb = QtWidgets.QCheckBox(f'{p}   ·   {desc}')
                perk.full(cb)
                attach_help(cb, 'equipment.perk', 'Equipment perks')
                self.eq_perks[p] = cb
            self.eq_perk_note = QtWidgets.QLabel()
            self.eq_perk_note.setObjectName('Derived')
            self.eq_perk_note.setWordWrap(True)
            perk.full(self.eq_perk_note)
            self.lay.addWidget(perk)

        self.lay.addWidget(self.flags.card)
        self.lay.addStretch(1)

        self.on(self.code.currentIndexChanged, lambda _: self._code())
        self.on(self.rarity.changed, lambda v: set_key(self.m, 'rarity', v, KEY_ORDER[section]))
        self.on(self.level.valueChanged, lambda v: set_key(self.m, 'level', v, KEY_ORDER[section]))
        self.on(self.damage.changed, lambda: set_key(self.m, 'damage', self.damage.value(), KEY_ORDER[section]))
        for s, f in self.stats.items():
            self.on(f.changed, lambda s=s, f=f: self._stat(s, f))
        self.on(self.tree.changed, self._sockets)
        if self.weapon:
            self.on(self.perk_on.toggled, lambda _: self._perk())
            self.on(self.cause.currentIndexChanged, lambda _: self._perk())
            self.on(self.effect.currentIndexChanged, lambda _: self._perk())
            self.on(self.eff.valueChanged, lambda _: self._perk())
            self.on(self.value_default.toggled, lambda _: self._perk())
            self.on(self.value.valueChanged, lambda _: self._perk())
        else:
            for cb in self.eq_perks.values():
                self.on(cb.toggled, lambda _: self._eq_perk())

    # model -> widgets
    def load(self):
        m = self.m
        code = m.get('code')
        set_combo(self.code, code)
        r = m.get('rarity', 'legendary')
        self.rarity.set(core.RARITIES[r] if isinstance(r, int) and 0 <= r <= 4 else str(r).lower())
        lvl = m.get('level', core.MAX_LEVEL)
        self.level.blockSignals(True)
        self.level.setValue(lvl if isinstance(lvl, int) else core.MAX_LEVEL)
        self.level.blockSignals(False)
        self.level_slider.setValue(self.level.value())
        self.refresh_ranges()
        self.damage.set_value(m.get('damage'))
        stats = m.get('stats') if isinstance(m.get('stats'), dict) else {}
        for s, f in self.stats.items():
            f.set_value(stats.get(self.stat_key(s)))
        socks = m.get('sockets') or {}
        if isinstance(socks, list):
            socks = {'main': socks}
        self.tree.set_data(socks if isinstance(socks, dict) else {}, self.rarity_index(), bool(m.get('perk')))
        if self.weapon:
            p = m.get('perk') if isinstance(m.get('perk'), dict) else None
            self.perk_on.setChecked(p is not None)
            set_combo(self.cause, (p or {}).get('cause', 'on_enemy_hit'))
            set_combo(self.effect, (p or {}).get('effect', 'boomerang_at_target'))
            eff = (p or {}).get('efficiency', 1.0)
            self.eff.setValue(float(eff) if isinstance(eff, (int, float)) else 1.0)
            v = (p or {}).get('value', 'default')
            self.value_default.setChecked(v == 'default')
            self.value.setValue(float(v) if isinstance(v, (int, float)) else self.default_value())
        else:
            perks = m.get('perk') or []
            perks = [perks] if isinstance(perks, str) else perks
            for p, cb in self.eq_perks.items():
                cb.setChecked(p in perks)
        self.flags.load(m)
        self.after_edit()

    def rarity_index(self):
        r = self.rarity.value()
        return core.RARITIES.index(r) if r in core.RARITIES else 4

    def default_value(self):
        return core.default_perk_value(self.code.currentData() or 'smg', self.cause.currentData())

    def refresh_ranges(self):
        code = self.code.currentData()
        lo, hi = core.damage_range(self.rarity_index(), self.level.value() - 1)
        self.damage.set_range(lo, hi)
        if self.weapon and code in core.WEAPONS:
            for s, f in self.stats.items():
                f.set_range(*core.stat_range(code, self.stat_key(s)))
            rate = self.stat_key('rate')
            if self.rate_label.text() != STAT_TITLES[rate]:
                self.rate_label.setText(STAT_TITLES[rate])
                self.rate_help.set_help(f'weapon.stats.{rate}', STAT_TITLES[rate])
                attach_help(self.stats['rate'], f'weapon.stats.{rate}', STAT_TITLES[rate], replace=True)

    def stat_key(self, s):
        if s != 'rate':
            return s
        code = self.code.currentData()
        return 'charge_time' if code in core.WEAPONS and 'charge_time' in core.weapon_stats(code) else 'fire_rate'

    def after_edit(self):
        """Refresh everything derived from the current values."""
        self.refresh_ranges()
        code = self.code.currentData() or '?'
        r = self.rarity_index()
        names = WEAPON_NAMES if self.weapon else EQUIPMENT_NAMES
        self.title.setText(f'{names.get(code, code)}')
        self.title.setStyleSheet(f'color:{RARITY_COLOURS[r]};')
        if self.weapon:
            cat = core.WEAPON_CATEGORY.get(code, '?')
            who = f' · {PRIMARY_CLASS[code]} primary (other classes need the weapon hack)' if code in PRIMARY_CLASS else ''
            self.sub.setText(f'{core.RARITIES[r].capitalize()} {cat} weapon · level {self.level.value()}{who}')
        else:
            self.sub.setText(f'{core.RARITIES[r].capitalize()} equipment · level {self.level.value()}')
        if code in core.DLC_ITEMS:
            self.sub.setText(self.sub.text() + f' · needs the {core.DLC_ITEMS[code]} add-on')
        self.update_entry_actions()
        self.flags.paint_tints(r)
        self.tree.rarity = r
        self.tree.perk = bool(self.m.get('perk')) if self.m is not None else False
        self.tree.update()
        if self.weapon:
            on = self.perk_on.isChecked()
            for w in (self.cause, self.effect, self.eff, self.eff_slider, self.value_default):
                w.setEnabled(on)
            self.value.setEnabled(on and not self.value_default.isChecked())
            dv = self.default_value()
            self.value_hint.setText(f'default for {code}: {dv:.4g}')
            if on:
                v = dv if self.value_default.isChecked() else self.value.value()
                self.perk_summary.setText(f'Triggers: {core.perk_trigger_text(self.cause.currentData(), v)}\n'
                                          f'Effect: {core.perk_effect_text(self.effect.currentData(), self.level.value(), self.eff.value())}')
            else:
                self.perk_summary.setText('')
        else:
            applied = core.EQUIPMENT_PERKS_APPLIED.get(code, set())
            ignored = [p for p, cb in self.eq_perks.items() if cb.isChecked() and p not in applied]
            self.eq_perk_note.setText(f'{code} ignores {", ".join(ignored)} (not in its attribute list)' if ignored else
                                      f'{code} applies: {", ".join(sorted(applied))}')

    # widgets -> model
    def _code(self):
        code = self.code.currentData()
        set_key(self.m, 'code', code, KEY_ORDER[self.section])
        if self.weapon:
            stats = self.m.get('stats')
            if isinstance(stats, dict):
                for s in list(stats):
                    if s not in core.weapon_stats(code):
                        del stats[s]
                if not stats:
                    del_key(self.m, 'stats')
            if isinstance(self.m.get('equip'), str):
                set_key(self.m, 'equip', True, KEY_ORDER[self.section])
            if self.m.get('equip'):               # moving to another category: free the old slot, take the new
                self.flags.give_back()
                self.flags.claim_slot()
            self.loading = True
            for s, f in self.stats.items():
                f.set_range(*core.stat_range(code, self.stat_key(s)))
                f.set_value((self.m.get('stats') or {}).get(self.stat_key(s)))
            self.loading = False

    def _stat(self, s, f):
        s = self.stat_key(s)
        v = f.value()
        stats = self.m.get('stats')
        if v == 'max' and not isinstance(stats, dict):
            return
        stats = child_map(self.m, 'stats', KEY_ORDER[self.section])
        if v == 'max' and s not in stats:
            return
        set_key(stats, s, v, KEY_ORDER['stats'])

    def _sockets(self):
        g = self.tree.groups
        old = self.m.get('sockets')
        if not any(g.values()):
            del_key(self.m, 'sockets')
            return
        if not self.weapon:
            if isinstance(old, list) and list(old) == g['main']:
                return
            seq = flow_seq(g['main'])
            set_key(self.m, 'sockets', seq, KEY_ORDER[self.section])
            return
        if isinstance(old, list) and not g['branch1'] and not g['branch2']:
            if list(old) != g['main']:
                set_key(self.m, 'sockets', flow_seq(g['main']), KEY_ORDER[self.section])
            return
        socks = old if isinstance(old, dict) else None
        if socks is None:
            socks = CommentedMap()
            set_key(self.m, 'sockets', socks, KEY_ORDER[self.section])
        for k in ('main', 'branch1', 'branch2'):
            cur = socks.get(k)
            if not g[k]:
                del_key(socks, k)
            elif not (isinstance(cur, list) and list(cur) == g[k]):
                seq = flow_seq(g[k])
                if isinstance(cur, CommentedSeq) and cur.fa.flow_style() is False:
                    seq = CommentedSeq(g[k])
                set_key(socks, k, seq, KEY_ORDER['sockets'])

    def _perk(self):
        if not self.perk_on.isChecked():
            del_key(self.m, 'perk')
            return
        p = child_map(self.m, 'perk', KEY_ORDER[self.section], flow=True)
        set_key(p, 'cause', self.cause.currentData(), KEY_ORDER['perk'])
        set_key(p, 'effect', self.effect.currentData(), KEY_ORDER['perk'])
        set_key(p, 'efficiency', round(self.eff.value(), 2), KEY_ORDER['perk'])
        if self.value_default.isChecked():
            del_key(p, 'value')
        else:
            set_key(p, 'value', round(self.value.value(), 4), KEY_ORDER['perk'])

    def _eq_perk(self):
        on = [p for p, cb in self.eq_perks.items() if cb.isChecked()]
        if not on:
            del_key(self.m, 'perk')
        elif len(on) == 1:
            set_key(self.m, 'perk', on[0], KEY_ORDER[self.section])
        else:
            set_key(self.m, 'perk', flow_seq(on), KEY_ORDER[self.section])



def palette_icon(ink):
    """A small painter's-palette icon in one colour, for the colour picker button."""
    pm = QtGui.QPixmap(36, 36)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(ink), 1.4))
    outline = QtGui.QPainterPath()
    outline.addEllipse(QtCore.QRectF(1.5, 2.5, 15, 13))
    hole = QtGui.QPainterPath()
    hole.addEllipse(QtCore.QRectF(9.5, 9.5, 3.6, 3.2))           # thumb hole
    p.drawPath(outline.subtracted(hole))
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor(ink))
    for x, y in ((5.5, 8), (8.5, 5.5), (12.5, 6)):                # paint dabs
        p.drawEllipse(QtCore.QPointF(x, y), 1.5, 1.5)
    p.end()
    return QtGui.QIcon(pm)


class ColourEdit(QtWidgets.QWidget):
    """A typed "#rrggbb" value with a swatch button beside it that opens a colour picker."""
    picked = Signal()

    def __init__(self):
        super().__init__()
        self.colour = QtGui.QColor('#808080')
        self.kept = False
        hl = QtWidgets.QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self.text = QtWidgets.QLineEdit()
        self.text.setFixedWidth(92)
        self.text.setMaxLength(7)
        self.text.setStyleSheet('font-family: Menlo, monospace; font-size: 12px;')
        self.text.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression('#?[0-9A-Fa-f]{0,6}')))
        self.text.setToolTip('Type a colour as #rrggbb, then press Return')
        self.text.textEdited.connect(self._preview)
        self.text.editingFinished.connect(self._typed)
        self.swatch = QtWidgets.QPushButton()
        self.swatch.setFixedSize(28, 28)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.setToolTip('Choose a colour')
        self.swatch.setIconSize(QtCore.QSize(18, 18))
        self.swatch.clicked.connect(self._pick)
        hl.addWidget(self.text)
        hl.addWidget(self.swatch)
        self._paint()

    def set_colour(self, c):
        self.colour = QtGui.QColor(c)
        self._paint()

    def set_kept(self, kept):
        """kept: the area isn't set, so the equipped set's colour is used (shown as "kept")."""
        self.kept = kept
        self.text.setEnabled(not kept)
        self.swatch.setEnabled(not kept)
        self._paint()

    def _paint(self, shown=None):
        if self.kept:
            self.text.setText('kept')
            self.swatch.setIcon(palette_icon(FAINT))
            self.swatch.setStyleSheet(f'QPushButton {{ background:{BG}; border:1px dashed {BORDER}; '
                                      f'border-radius:7px; }}')
            return
        if shown is None:
            shown = self.colour
            self.text.setText(shown.name())
        light = 0.299 * shown.red() + 0.587 * shown.green() + 0.114 * shown.blue() > 140
        self.swatch.setIcon(palette_icon('#111111' if light else '#f2f2f2'))
        self.swatch.setStyleSheet(f'QPushButton {{ background:{shown.name()}; border:2px solid {BORDER}; '
                                  f'border-radius:7px; }} QPushButton:hover {{ border-color:{ACCENT}; }}')

    @staticmethod
    def _parse(text):
        t = text.strip().lstrip('#')
        return QtGui.QColor('#' + t) if len(t) == 6 else None

    def _preview(self, text):
        c = self._parse(text)
        if c is not None:
            self._paint(c)                          # swatch follows the typing; the value is set on Return

    def _typed(self):
        c = self._parse(self.text.text())
        if c is None or c == self.colour:
            self._paint()                           # incomplete or unchanged: show the current value again
            return
        self.set_colour(c)
        self.picked.emit()

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(self.colour, self, 'Armor colour')
        if c.isValid():
            self.set_colour(c)
            self.picked.emit()


def effect_meaning(code, v):
    """Plain description of an armor effect value, e.g. '+5% movement speed (upside)'."""
    neutral, direction = core.ARMOR_EFFECTS[code]
    if core.same32(v, neutral):
        return 'no effect (neutral value)'
    side = 'upside' if (v - neutral) * direction > 0 else 'downside'
    if code.startswith('ability_recharge'):
        return f'ability {code[-1]} recharges {abs(v):g} s {"faster" if v < 0 else "slower"} ({side})'
    what = {'movement_speed': 'movement speed', 'max_hp_multiplier': 'max HP', 'rush_recharge': 'rush recharge',
            'health_drop_rate': 'health drops', 'ability_drop_rate': 'ability drops'}[code]
    return f'{(v - 1) * 100:+.0f}% {what} ({side})'.replace('-', '−')


def show_kept(sp, value):
    """Spin box display: None shows "kept" (kept from the worn set, disabled), else the value."""
    sp.blockSignals(True)
    if value is None:
        sp.setSpecialValueText('kept')
        sp.setMinimum(-1)
        sp.setValue(-1)
        sp.setEnabled(False)
    else:
        sp.setSpecialValueText('')
        sp.setMinimum(0)
        sp.setValue(value)                  # above the maximum (some stock sets store 2) shows as 1: the
                                            # game caps the result at 1, so it looks the same
        sp.setEnabled(True)
    sp.blockSignals(False)


def floats_to_hex(vals):
    r, g, b = (max(0, min(255, round(float(x) * 255))) for x in vals[:3])
    return f'#{r:02x}{g:02x}{b:02x}'


class ArmorEditor(Editor):
    def __init__(self, main):
        super().__init__(main)
        self.header('Armor set')
        self.entry_actions()
        basics = Card('Set')
        self.rarity = Segmented([(0, 'Stock (0)'), (1, 'Looted (1)'), (2, '2'), (3, '3'), (4, '4')],
                                [RARITY_COLOURS[0], RARITY_COLOURS[1], LEVEL_COLOURS['untested'],
                                 LEVEL_COLOURS['untested'], LEVEL_COLOURS['untested']])
        for i in (2, 3, 4):                      # untested rarities: the ▲ marker, as elsewhere
            btn = self.rarity.group.button(i)
            btn.setIcon(glyph_icon(LEVEL_GLYPH['untested'], LEVEL_COLOURS['untested'], 12))
            btn.setIconSize(QtCore.QSize(12, 12))
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setLayoutDirection(Qt.RightToLeft)          # marker after the number, like "Unobtainium ▲"
            btn.setToolTip('Untested: game-made armor sets are stock (0) or looted (1)')
        basics.row('Rarity', self.rarity, 'armor.rarity')
        lv, self.level_slider, self.level = slider_spin(1, core.MAX_LEVEL)
        basics.row('Level', lv, 'armor.level')
        self.flags = EntryFlags(self, 'armor_sets', basics)
        self.lay.addWidget(basics)

        colours = Card('Colours', 'armor.colors', 'Glow makes an area give off light in its colour, as an even '
                                                 'fill over the whole area; game-made sets only give the visor '
                                                 'a faint glow. Untick a setting to keep it from the set you are '
                                                 'wearing when the savegame is saved.')
        finish = Card('Finish', 'armor.finish', 'Metallic and shine each have two separate settings: one for the '
                                                'armor\'s surface and one for its details. The '
                                                'armor\'s own texture decides which parts are which. Set both the '
                                                'same for an even finish.')
        self.areas, self.words = {}, {}

        def header(card, *rows):
            w = QtWidgets.QWidget()
            vl = QtWidgets.QVBoxLayout(w)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            for cols in rows:
                hl = QtWidgets.QHBoxLayout()
                hl.setSpacing(0)
                for text, width in cols:
                    lab = QtWidgets.QLabel(text)
                    lab.setObjectName('Muted')
                    lab.setFixedWidth(width)
                    hl.addWidget(lab)
                hl.addStretch(1)
                vl.addLayout(hl)
            card.row('', w)

        def spin(top):
            sp = QtWidgets.QDoubleSpinBox()
            sp.setRange(0, top)
            sp.setDecimals(2)
            sp.setSingleStep(0.05)
            sp.setFixedWidth(60)
            sp.setKeyboardTracking(False)
            return sp

        def tick(tip):
            cb = QtWidgets.QCheckBox()
            cb.setFixedWidth(26)
            cb.setToolTip(tip)
            return cb

        def line(*parts):
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(0)
            for part in parts:
                if isinstance(part, int):
                    hl.addSpacing(part)
                else:
                    hl.addWidget(part)
            hl.addStretch(1)
            return w

        header(colours, [('Colour', 26 + 92 + 6 + 28 + 24), ('Glow (0 none – 1 full)', 26 + 60 + 80)])
        pair = 26 + 60 + 8 + 60 + 24                    # tick, surface, gap, details, gap to the next pair
        header(finish, [('Metallic (0 none – 1 full)', pair), ('Shine (0 none – 1 full)', pair)],
               [('', 26), ('Surface', 68), ('Details', 60 + 24 + 26), ('Surface', 68), ('Details', 60)])
        for area in core.ARMOR_AREAS_MENU:
            title = area.capitalize()
            c_on, btn = tick('Tick to set the colour; untick to keep the worn set\'s'), ColourEdit()
            g_on, glow = tick('Tick to set the glow; untick to keep the worn set\'s'), spin(1)
            attach_help(btn, 'armor.color', f'{title} colour')
            attach_help(glow, 'armor.glow', f'{title} glow')
            if area == 'accent':                       # the game ignores accent glow, so don't offer it
                never = QtWidgets.QLabel('never glows')
                never.setObjectName('Muted')
                colours.row(title, line(c_on, btn, 24 + 26 + 4, never), 'armor.colors', f'{title}: colour areas')
            else:
                boxes, glow_word = line(c_on, btn, 24, g_on, glow), QtWidgets.QLabel()
                glow_word.setObjectName('Muted')
                glow_word.setFixedWidth(60)
                glow_word.setAlignment(Qt.AlignCenter)
                self.words[area, 'glow'] = [glow_word]
                cell = QtWidgets.QWidget()
                vl = QtWidgets.QVBoxLayout(cell)
                vl.setContentsMargins(0, 0, 0, 0)
                vl.setSpacing(1)
                vl.addWidget(boxes)
                vl.addWidget(line(26 + 92 + 6 + 28 + 24 + 26, glow_word))
                colours.row(title, cell, 'armor.colors', f'{title}: colour areas', top=boxes.sizeHint().height())
            fin, parts, word_parts = {}, [], []
            for key in core.ARMOR_FINISH:
                f_on, surface, details = tick(f'Tick to set the {key}; untick to keep the worn set\'s'), spin(1), spin(1)
                for sp_, part in ((surface, 'surface'), (details, 'details')):
                    attach_help(sp_, f'armor.{key}', f'{title} {key}: {part}')
                words = []
                for _ in range(2):                     # the scale word under each box
                    lab = QtWidgets.QLabel()
                    lab.setObjectName('Muted')
                    lab.setFixedWidth(60)
                    lab.setAlignment(Qt.AlignCenter)
                    words.append(lab)
                self.words[area, key] = words
                parts += ([24] if parts else []) + [f_on, surface, 8, details]
                word_parts += ([24] if word_parts else []) + [26, words[0], 8, words[1]]
                fin[key] = (f_on, surface, details)
                self.on(f_on.toggled, lambda _, a=area, k=key: self._finish(a, k))
                self.on(surface.valueChanged, lambda _, a=area, k=key: self._finish(a, k))
                self.on(details.valueChanged, lambda _, a=area, k=key: self._finish(a, k))
            cell = QtWidgets.QWidget()
            vl = QtWidgets.QVBoxLayout(cell)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(1)
            boxes = line(*parts)
            vl.addWidget(boxes)
            vl.addWidget(line(*word_parts))
            lab = finish.row(title, cell, 'armor.finish', f'{title} finish', top=boxes.sizeHint().height())
            lab.setText(f'{title} <a href="use" style="color:{TEAL}; text-decoration:none;">(use default)</a>')
            lab.setToolTip(f'Use default: sets the {title.lower()}\'s metallic and shine to what game-made armor '
                           f'sets usually give it. A good place to start.')
            self.on(lab.linkActivated, lambda _, a=area: self._use_typical(a))
            self.areas[area] = {'color': (c_on, btn), 'glow': (g_on, glow), **fin}
            self.on(c_on.toggled, lambda _, a=area: self._colour(a))
            self.on(btn.picked, lambda a=area: self._colour(a))
            self.on(g_on.toggled, lambda _, a=area: self._glow(a))
            self.on(glow.valueChanged, lambda _, a=area: self._glow(a))
        self.lay.addWidget(colours)
        self.lay.addWidget(finish)

        eff = Card('Effects', 'armor.effects', 'Game-made looted sets carry exactly two of the rolled values.')
        self.eff_box = QtWidgets.QVBoxLayout()
        self.eff_box.setSpacing(8)
        eff.body.addLayout(self.eff_box)
        add = QtWidgets.QPushButton('+ Add effect')
        add.clicked.connect(self._add_effect)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(add)
        hl.addStretch(1)
        eff.body.addLayout(hl)
        self.lay.addWidget(eff)
        self.eff_rows = []

        self.lay.addStretch(1)
        self.on(self.rarity.changed, lambda v: set_key(self.m, 'rarity', v, KEY_ORDER['armor_sets']))
        self.on(self.level.valueChanged, lambda v: set_key(self.m, 'level', v, KEY_ORDER['armor_sets']))

    def area_key(self, area):
        cols = self.m.get('colors') if isinstance(self.m.get('colors'), dict) else {}
        for k in cols:
            if k == area:
                return k
        return None

    def area_settings(self, area):
        """This area's plan settings as a dict (a bare colour counts as {color: ...})."""
        cols = self.m.get('colors') if isinstance(self.m.get('colors'), dict) else {}
        k = self.area_key(area)
        v = cols.get(k) if k is not None else None
        return v if isinstance(v, dict) else ({} if v is None else {'color': v})

    def load(self):
        m = self.m
        r = m.get('rarity', 1)
        self.rarity.set(core.RARITIES.index(r) if r in core.RARITIES else r)
        self.level.setValue(m.get('level', core.MAX_LEVEL) if isinstance(m.get('level'), int) else core.MAX_LEVEL)
        for area, w in self.areas.items():
            v = self.area_settings(area)
            c_on, btn = w['color']
            c_on.setChecked('color' in v)
            try:
                vals = core.parse_colour(v['color'], area) if 'color' in v else [0.5, 0.5, 0.5, 0]
            except core.PlanError:
                vals = [0.5, 0.5, 0.5, 0]
            btn.set_colour(floats_to_hex(vals[:3]))
            btn.set_kept('color' not in v)
            g_on, glow = w['glow']
            g = v.get('glow')
            g_on.setChecked(g is not None)
            show_kept(glow, None if g is None else float(g))
            if area != 'accent':
                self._show_words(area, 'glow')
            for key in core.ARMOR_FINISH:
                f_on, surface, details = w[key]
                val = v.get(key)
                pair = val if isinstance(val, list) and len(val) == 2 else [val, val] if val is not None else None
                f_on.setChecked(pair is not None)
                show_kept(surface, None if pair is None else float(pair[0]))
                show_kept(details, None if pair is None else float(pair[1]))
                self._show_words(area, key)
        self._load_effects()
        self.flags.load(m)
        self.after_edit()

    def after_edit(self):
        r = self.rarity.value()
        r = r if isinstance(r, int) else 1
        n = len(self.eff_rows)
        self.update_entry_actions()
        self.title.setText('Armor set')
        self.title.setStyleSheet(f'color:{RARITY_COLOURS[min(r, 4)]};')
        self.sub.setText(f'{"Stock" if r == 0 else "Looted" if r == 1 else f"Rarity {r}"} set · level '
                         f'{self.level.value()} · {n} effect{"s" * (n != 1)}')

    def _setting(self, area, key, value):
        """Set (or, with None, remove) one of this area's settings, leaving the others as they are."""
        k = self.area_key(area)
        cols = child_map(self.m, 'colors', KEY_ORDER['armor_sets'])
        cur = cols.get(k) if k is not None else None
        if not isinstance(cur, dict):
            cur = CommentedMap() if cur is None else CommentedMap([('color', cur)])
        if value is None:
            del_key(cur, key)
        else:
            set_key(cur, key, value, list(core.ARMOR_AREA_KEYS))
        if cur:
            set_key(cols, k if k is not None else area, cur, KEY_ORDER['colors'])
        else:
            if k is not None:
                del cols[k]
            if not cols:
                del self.m['colors']

    def _colour(self, area):
        c_on, btn = self.areas[area]['color']
        btn.set_kept(not c_on.isChecked())
        self._setting(area, 'color', btn.colour.name() if c_on.isChecked() else None)

    def _glow(self, area):
        g_on, glow = self.areas[area]['glow']
        if not g_on.isChecked():
            show_kept(glow, None)
        elif glow.minimum() < 0:                     # just ticked: start from no glow
            show_kept(glow, 0.0)
        self._show_words(area, 'glow')
        self._setting(area, 'glow', round(glow.value(), 3) if g_on.isChecked() else None)

    def _show_words(self, area, key):
        for sp, lab in zip(self.areas[area][key][1:], self.words[area, key]):
            lab.setText(core.scale_word(key, sp.value()) if sp.minimum() >= 0 else '')

    def _use_typical(self, area):
        """Set the area's metallic and shine to what game-made sets usually have."""
        for key, t in core.ARMOR_FINISH_TYPICAL[area].items():
            f_on, surface, details = self.areas[area][key]
            lo, hi = t if isinstance(t, list) else (t, t)
            f_on.blockSignals(True)
            f_on.setChecked(True)
            f_on.blockSignals(False)
            show_kept(surface, float(lo))
            show_kept(details, float(hi))
            self._finish(area, key)

    def _finish(self, area, key):
        f_on, surface, details = self.areas[area][key]
        if not f_on.isChecked():
            show_kept(surface, None)
            show_kept(details, None)
            self._show_words(area, key)
            self._setting(area, key, None)
            return
        if surface.minimum() < 0:                      # just ticked: start from the game's usual finish
            t = core.ARMOR_FINISH_TYPICAL[area][key]
            lo, hi = t if isinstance(t, list) else (t, t)
            show_kept(surface, float(lo))
            show_kept(details, float(hi))
        self._show_words(area, key)
        lo, hi = round(surface.value(), 3), round(details.value(), 3)
        self._setting(area, key, lo if lo == hi else flow_seq([lo, hi]))

    # effects
    def _effects_list(self):
        e = self.m.get('effects')
        if isinstance(e, dict):
            return [(k, v) for k, v in e.items()]
        if isinstance(e, list):
            return [next(iter(x.items())) for x in e if isinstance(x, dict) and x]
        return []

    def _load_effects(self):
        for row in self.eff_rows:
            discard(row[0])
        self.eff_rows = []
        for code, value in self._effects_list():
            self._effect_row(code, value)

    def _effect_row(self, code, value):
        """One effect: which one, its value (a value the game rolls, or Custom) and what that means."""
        w = QtWidgets.QFrame()
        w.setObjectName('EffectRow')
        w.setStyleSheet(f'QFrame#EffectRow {{ border: 1px solid {BORDER}; border-radius: 8px; }}')
        outer = QtWidgets.QVBoxLayout(w)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)
        top = QtWidgets.QHBoxLayout()
        c = QtWidgets.QComboBox()
        for k in core.ARMOR_EFFECTS:
            c.addItem(f'{ARMOR_EFFECT_TITLES[k]}   ({k})', k)
        set_combo(c, code)
        vals = QtWidgets.QComboBox()
        vals.setToolTip('The values the game\'s loot generator gives this effect ("rolled"), or Custom for '
                        'your own number (Custom values need "Allow untested")')
        vals.setMinimumWidth(150)
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(-100, 100)
        s.setDecimals(3)
        s.setSingleStep(0.05)
        s.setKeyboardTracking(False)
        s.setFixedWidth(90)
        try:
            s.setValue(float(value))
        except (TypeError, ValueError):
            pass
        rm = QtWidgets.QToolButton()
        rm.setText('✕')
        rm.setToolTip('Remove this effect')
        top.addWidget(c, 1)
        top.addWidget(vals)
        top.addWidget(s)
        top.addWidget(rm)
        outer.addLayout(top)
        meaning = QtWidgets.QLabel()
        meaning.setObjectName('Derived')
        outer.addWidget(meaning)

        def game_values():
            return [v for v in core.ARMOR_EFFECT_GENERATED[c.currentData()] if v is not None]

        def fill_values():
            vals.blockSignals(True)
            vals.clear()
            for v in game_values():
                vals.addItem(f'{v:g} (rolled)', v)
            vals.addItem('Custom', 'custom')
            vals.blockSignals(False)

        def sync():
            """Select the dropdown entry matching the number; update the meaning and untested warning."""
            k, v = c.currentData(), s.value()
            match = next((g for g in game_values() if core.same32(v, g)), None)
            i = vals.findData(match if match is not None else 'custom')
            vals.blockSignals(True)
            vals.setCurrentIndex(i)
            vals.blockSignals(False)
            s.setVisible(match is None)
            meaning.setText(effect_meaning(k, v) + ('' if match is not None else
                                                    '  ·  not a value the game rolls (needs Allow untested)'))
            s.setProperty('warn', match is None)
            s.style().unpolish(s)
            s.style().polish(s)

        def picked(i):
            v = vals.itemData(i)
            if v == 'custom':
                s.setVisible(True)
                s.setFocus()
                s.selectAll()
                return
            s.setValue(v)            # valueChanged updates the plan

        fill_values()
        sync()
        attach_help(w, 'armor.effects', 'Armor effect')
        row = (w, c, s)
        self.eff_rows.append(row)
        self.eff_box.addWidget(w)

        def code_changed():
            fill_values()
            g = game_values()
            if g and not any(core.same32(s.value(), x) for x in g):
                s.blockSignals(True)
                s.setValue(g[0])                 # a new effect starts at its first rolled value
                s.blockSignals(False)
            sync()
        self.on(c.currentIndexChanged, lambda _: (code_changed(), self._write_effects()))
        self.on(vals.activated, picked)
        self.on(s.valueChanged, lambda _: (sync(), self._write_effects()))
        rm.clicked.connect(lambda: self._remove_effect(row))

    def _add_effect(self):
        used = {c.currentData() for _, c, _ in self.eff_rows}
        code = next((k for k in core.ARMOR_EFFECTS if k not in used), 'movement_speed')
        good = [v for v in core.ARMOR_EFFECT_GENERATED[code] if v is not None]
        self.loading = True
        self._effect_row(code, good[0])
        self.loading = False
        self._write_effects()
        self.after_edit()
        self.commit()

    def _remove_effect(self, row):
        self.eff_rows.remove(row)
        discard(row[0])
        self._write_effects()
        self.after_edit()
        self.commit()

    def _write_effects(self):
        items = [(c.currentData(), round(s.value(), 3)) for _, c, s in self.eff_rows]
        items = [(k, int(v) if k.startswith('ability_recharge') and float(v).is_integer() else v) for k, v in items]
        if not items:
            del_key(self.m, 'effects')
            return
        old = self.m.get('effects')
        dupes = len({k for k, _ in items}) != len(items)
        if isinstance(old, list) or dupes:
            val = CommentedSeq([flow_map([(k, v)]) for k, v in items])
        else:
            val = old if isinstance(old, dict) else CommentedMap()
            for k in list(val):
                del val[k]
            for k, v in items:
                val[k] = v
        set_key(self.m, 'effects', val, KEY_ORDER['armor_sets'])



class ProfileEditor(Editor):
    def __init__(self, main):
        super().__init__(main)
        self.header('Profile', 'Character resources and levels. Fields left at "—" are not touched.')
        self.base_sub = self.sub.text()
        lv = Card('Levels')
        self.level = OptSpin(1, core.MAX_LEVEL)
        self.hero = OptSpin(1, core.MAX_HERO)
        lv.row('Player level', self.level, 'profile.level')
        lv.row('Hero level', self.hero, 'profile.hero_level')
        self.xp_note = QtWidgets.QLabel()
        self.xp_note.setObjectName('Derived')
        self.xp_note.setVisible(False)
        lv.full(self.xp_note)
        self.lay.addWidget(lv)

        keys = Card('Keys, credits and Xenoflowers')
        self.keys = {}
        for k, title in (('ufo', 'UFO keys'), ('ark', 'Ark Ship keys')):
            s = OptSpin(0, 999999)
            keys.row(title, s, 'profile.keys', title)
            self.keys[k] = s
        self.credits = OptSpin(0, 2_000_000_000)
        keys.row('Credits', self.credits, 'profile.credits')
        self.flowers = OptSpin(0, 999999)
        keys.row('Xenoflowers', self.flowers, 'profile.flowers')
        self.lay.addWidget(keys)

        cores = Card('Loose cores', 'profile.cores', 'Count per core type and level. "—" leaves a count unchanged.')
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)               # as Card's grid, so L1 starts at the other cards' inputs
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, LABEL_WIDTH)
        grid.setColumnStretch(7, 1)                 # spare width goes to the right, not the name column
        for lvl in range(1, 7):
            h = QtWidgets.QLabel(f'L{lvl}')
            h.setObjectName('Muted')
            h.setAlignment(Qt.AlignCenter)
            grid.addWidget(h, 0, lvl)
        self.cores = {}
        for row, (name, t) in enumerate(core.CORES.items(), start=1):
            lab = QtWidgets.QLabel(f'  {name.capitalize()}')
            lab.setPixmap(dot_icon(CORE_COLOURS[t], 14).pixmap(14, 14))
            nm = QtWidgets.QLabel(name.capitalize())
            box = QtWidgets.QHBoxLayout()
            box.setSpacing(6)
            box.addWidget(lab)
            box.addWidget(nm)
            box.addStretch(1)
            grid.addLayout(box, row, 0)
            for lvl in range(1, 7):
                s = OptSpin(0, 999999)
                s.setMinimumWidth(70)
                attach_help(s, 'profile.cores', f'{name.capitalize()} cores, level {lvl}')
                grid.addWidget(s, row, lvl)
                self.cores[(t, lvl)] = s
        cores.body.addLayout(grid)
        self.lay.addWidget(cores)

        metals = Card('Metals', 'profile.metals')
        self.metals = {}
        for k in core.METALS:
            s = OptSpin(0, 999999)
            untested = f' <span style="color:{LEVEL_COLOURS["untested"]}">{LEVEL_GLYPH["untested"]}</span>'
            lab = metals.row(METAL_TITLES[k] + (untested if k == 'unobtainium' else ''), s, 'profile.metals',
                             METAL_TITLES[k])
            if k == 'unobtainium':
                lab.setToolTip('Untested: no game-made savegame has unobtainium, so setting it needs '
                               '"Allow untested values" (Settings)')
            self.metals[k] = s
        self.lay.addWidget(metals)

        self.lay.addStretch(1)

        self.on(self.level.valueChanged, lambda _: self._set('level', self.level.opt()))
        self.on(self.hero.valueChanged, lambda _: self._set('hero_level', self.hero.opt()))
        for k, s in self.keys.items():
            self.on(s.valueChanged, lambda _, k=k, s=s: self._sub('keys', k, s.opt(), ['ufo', 'ark']))
        self.on(self.credits.valueChanged, lambda _: self._set('credits', self.credits.opt()))
        for (t, lvl), s in self.cores.items():
            self.on(s.valueChanged, lambda _, t=t, lvl=lvl, s=s: self._core(t, lvl, s.opt()))
        for k, s in self.metals.items():
            self.on(s.valueChanged, lambda _, k=k, s=s: self._sub('metals', k, s.opt(), list(core.METALS)))
        self.on(self.flowers.valueChanged, lambda _: self._set('flowers', self.flowers.opt()))

    def prof(self):
        return self.main.doc.section_map('profile', create=True)

    def load(self):
        p = self.m if isinstance(self.m, dict) else {}
        self.level.set_opt(p.get('level'))
        self.hero.set_opt(p.get('hero_level'))
        keys = p.get('keys') or {}
        for k, s in self.keys.items():
            s.set_opt(keys.get(k))
        self.credits.set_opt(p.get('credits'))
        self.flowers.set_opt(p.get('flowers'))
        found = self._core_keys()
        for (t, lvl), s in self.cores.items():
            k = found.get((t, lvl))
            s.set_opt((p.get('cores') or {}).get(k) if k else None)
        metals = p.get('metals') or {}
        for k, s in self.metals.items():
            s.set_opt(metals.get(k))
        self.after_edit()

    def after_edit(self):
        main = self.main
        if main.session is not None and main.slot is not None:
            self.title.setText(character_short(main.slot, main.session.root['slots'][main.slot]))
            self.sub.setText(f'{display_path(main.session.path)} · Profile: '
                             f'{self.base_sub[0].lower()}{self.base_sub[1:]}')
        lvl, hero = self.level.opt(), self.hero.opt()
        if hero is not None:
            total = core.cumulative_xp(29, hero - 1)
            self.xp_note.setText(f'Hero level {hero} = {total:,} lifetime XP. Hero levels need player level 30.')
        elif lvl is not None:
            self.xp_note.setText(f'Level {lvl} = {core.cumulative_xp(lvl - 1, 0):,} lifetime XP.')
        else:
            self.xp_note.setText('')
        self.xp_note.setVisible(bool(self.xp_note.text()))

    def _core_keys(self):
        out = {}
        for k in (self.m or {}).get('cores') or {}:
            mm = re.fullmatch(r'([a-z]+)\s*(\d)', str(k).lower())
            t = (core.CORES.get(mm.group(1)) or core.CORE_ALIASES.get(mm.group(1))) if mm else None
            if t:
                out[(t, int(mm.group(2)))] = k
        return out

    def _ensure(self):
        if self.m is None or not isinstance(self.m, dict):
            self.m = self.prof()
        elif self.main.doc.data.get('profile') is not self.m:
            set_key(self.main.doc.data, 'profile', self.m, KEY_ORDER['root'])
        return self.m

    def _set(self, key, v):
        m = self._ensure()
        if v is None:
            del_key(m, key)
        else:
            set_key(m, key, v, KEY_ORDER['profile'])

    def _sub(self, sec, key, v, order):
        m = self._ensure()
        if v is None:
            if isinstance(m.get(sec), dict):
                del_key(m[sec], key)
            return
        set_key(child_map(m, sec, KEY_ORDER['profile']), key, v, order)

    def _core(self, t, lvl, v):
        k = self._core_keys().get((t, lvl), f'{core.CORE_NAMES[t]}{lvl}')
        order = [f'{core.CORE_NAMES[tt]}{ll}' for tt in range(1, 5) for ll in range(6, 0, -1)]
        self._sub('cores', k, v, order)


# --- YAML view --------------------------------------------------------------------------------------

class YamlHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)

        def fmt(c, bold=False, italic=False):
            f = QtGui.QTextCharFormat()
            f.setForeground(QtGui.QColor(c))
            if bold:
                f.setFontWeight(QtGui.QFont.Bold)
            f.setFontItalic(italic)
            return f
        self.rules = [
            (re.compile(r'^\s*(?:- )?([A-Za-z_][\w]*)\s*:'), fmt('#7cc4ff'), 1),
            (re.compile(r'(?<=[{,]\s)([A-Za-z_]\w*)(?=:)'), fmt('#7cc4ff'), 1),
            (re.compile(r'\b-?\d+(?:\.\d+)?\b'), fmt('#f5a97f'), 0),
            (re.compile(r'\b(true|false|max|min|mid|default|null)\b'), fmt('#c792ea'), 0),
            (re.compile(r"'[^']*'|\"[^\"]*\""), fmt('#a6e3a1'), 0),
            (re.compile(r'\b(blue|red|yellow|white)\b'), fmt('#e6edf3', bold=True), 0),
        ]
        self.comment = fmt('#6b7789', italic=True)
        self.colours = {'blue': SOCKET_COLOURS['core1'], 'red': SOCKET_COLOURS['core2'],
                        'yellow': SOCKET_COLOURS['core3'], 'white': SOCKET_COLOURS['core']}

    def highlightBlock(self, text):
        for rx, f, grp in self.rules:
            for m in rx.finditer(text):
                if rx.pattern.startswith(r'\b(blue'):
                    f = QtGui.QTextCharFormat(f)
                    f.setForeground(QtGui.QColor(self.colours[m.group(1)]))
                self.setFormat(m.start(grp), m.end(grp) - m.start(grp), f)
        m = re.search(r'(^|\s)#.*$', text)
        if m and not re.match(r"^[^#]*'[^']*#", text):
            self.setFormat(m.start(), len(text) - m.start(), self.comment)


class DiffHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text):
        colour = {'+': '#4ade80', '-': '#f87171', '@': TEAL}.get(text[:1])
        if text.startswith(('+++', '---')):
            colour = MUTED
        if colour:
            f = QtGui.QTextCharFormat()
            f.setForeground(QtGui.QColor(colour))
            if text[:1] in '+-' and not text.startswith(('+++', '---')):
                f.setBackground(QtGui.QColor('#12301d' if text[:1] == '+' else '#3a1a1a'))
            self.setFormat(0, len(text), f)


# --- main window ------------------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.setWindowIcon(app_icon())
        self.resize(1480, 940)
        self.doc = PlanDoc()          # the shown character's working copy (placeholder while none is open)
        self.char_docs = {}           # slot -> working copy, kept while switching characters
        self.freed_by = {}            # id(entry) -> entries its Equip pushed out of their slot
        self.has_doc = False
        self.saved_plain = {}
        self.current_plain = {}
        self.session = None
        self.slot = None
        self.save_check = None            # (plan text, Report, savedata bytes or None) for the current plan
        self.write_target = None          # folder Savegame ▸ Save writes to
        self.save_check_timer = QtCore.QTimer(self, singleShot=True, interval=300, timeout=self.run_save_check)
        self.reports = {}
        self.history, self.hpos, self.last_push = [], -1, (0, None)
        self.text_timer = QtCore.QTimer(self, singleShot=True, interval=500, timeout=self.text_edited)
        self.input_polish = InputPolish(self)
        QtWidgets.QApplication.instance().installEventFilter(self.input_polish)
        self.build_ui()
        self.build_menus()
        self.show_start()
        # Open before the window is first shown, so the start page doesn't flash up first.
        if path:
            self.open_game_save(path)
        elif self.settings().value('open_last', True, type=bool):
            last = self.last_save()
            if last and os.path.exists(os.path.join(last, 'savedata.dat')):
                self.open_game_save(last, quiet=True)
        QtGui.QShortcut(QtGui.QKeySequence('F1'), self, activated=self.field_help)

    def set_yaml_visible(self, on):
        self.tabs.setTabVisible(0, on)
        if not on and self.tabs.currentIndex() == 0:
            self.tabs.setCurrentIndex(1)

    def tab_clicked(self, i):
        """A tab label always opens that tab, expanding the panel if it is collapsed. Expanding moves the
        tab bar, so it happens after the click is handled, then the clicked tab is selected again."""
        if i < 0:
            return
        self.tabs.setCurrentIndex(i)
        if self.right_collapsed:
            QtCore.QTimer.singleShot(0, lambda: (self.set_right_collapsed(False), self.tabs.setCurrentIndex(i)))

    def set_right_collapsed(self, collapsed):
        """Collapse the right panel to a vertical strip of its tabs (labels, counts and marks stay
        visible); clicking a tab or the « button expands it again."""
        stack = self.tabs.findChild(QtWidgets.QStackedWidget)
        sizes = self.split.sizes()
        if collapsed and not self.right_collapsed and sizes[2] > 60:
            self.right_width = sizes[2]
        was = self.right_collapsed
        self.right_collapsed = collapsed
        self.tabs.setTabPosition(QtWidgets.QTabWidget.East if collapsed else QtWidgets.QTabWidget.North)
        stack.setVisible(not collapsed)
        self.tabs.setCornerWidget(None if collapsed else self.collapse_btn, Qt.TopRightCorner)
        self.collapse_btn.setVisible(not collapsed)
        self.expand_btn.setVisible(collapsed)
        if collapsed:
            w = max(self.tabs.tabBar().sizeHint().width(), self.expand_btn.sizeHint().width()) + 6
            self.right_panel.setFixedWidth(w)
            if sizes[2]:
                self.split.setSizes([sizes[0], sizes[1] + sizes[2] - w, w])   # the editor gets the room
        else:
            self.right_panel.setMinimumWidth(0)
            self.right_panel.setMaximumWidth(16777215)
            if was and sizes[2]:
                want = getattr(self, 'right_width', 400)
                self.split.setSizes([sizes[0], max(300, sizes[1] + sizes[2] - want), want])
        self.settings().setValue('right_collapsed', collapsed)

    def build_settings_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        card = Card('Checks')
        self.untested = QtWidgets.QCheckBox('Allow untested values')
        self.untested.setToolTip('<qt>Accept values and combinations never seen in a game-made save (like the '
                                 'command line\'s --allow-untested).</qt>')
        self.untested.toggled.connect(lambda _: self.has_doc and self.refresh(text=False))
        card.full(self.untested)
        note = QtWidgets.QLabel(
            f'The marks in the list and the Checks tab:<br>'
            f'<span style="color:{LEVEL_COLOURS["error"]}">! error</span>: always blocks saving the savegame.<br>'
            f'<span style="color:{LEVEL_COLOURS["untested"]}">▲ untested</span>: something the game itself never '
            f'generates, e.g. custom effect values, perks the game never rolls, stats outside the rolled ranges, '
            f'or more sockets than the rarity has.<br>'
            f'<span style="color:{LEVEL_COLOURS["warning"]}">✓ warning</span>: a heads-up (e.g. needs an add-on); '
            f'never blocks saving.<br><br>'
            f'<b>Off</b> (recommended): <span style="color:{LEVEL_COLOURS["untested"]}">▲</span> untested values '
            f'are refused, so the savegame can\'t be saved.<br>'
            f'<b>On</b>: they become <span style="color:{LEVEL_COLOURS["warning"]}">✓</span> warnings and can be '
            f'saved, to test them. Try one at a time, on a copy of '
            f'your save. Applies to this window only and is not stored in the plan.')
        note.setObjectName('CardSub')
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        card.full(note)
        general = Card('General')
        self.confirm_quit = QtWidgets.QCheckBox('Ask to save before quitting or relaunching')
        self.confirm_quit.setChecked(self.settings().value('confirm_quit', True, type=bool))
        self.confirm_quit.toggled.connect(lambda on: self.settings().setValue('confirm_quit', on))
        general.full(self.confirm_quit)
        gnote = QtWidgets.QLabel('On (default): quitting with unsaved savegame changes asks whether to save them. '
                                 'Off: quitting discards them without asking. Opening or closing a savegame '
                                 'always asks. Remembered between launches.')
        gnote.setObjectName('CardSub')
        gnote.setWordWrap(True)
        general.full(gnote)
        self.open_last = QtWidgets.QCheckBox('Open the last savegame on launch')
        self.open_last.setChecked(self.settings().value('open_last', True, type=bool))
        self.open_last.toggled.connect(lambda on: self.settings().setValue('open_last', on))
        general.full(self.open_last)
        onote = QtWidgets.QLabel('On (default): the editor starts with the savegame you opened last, at slot 0. '
                                 'If it has been moved or deleted, you get the start page instead.')
        onote.setObjectName('CardSub')
        onote.setWordWrap(True)
        general.full(onote)
        self.show_yaml = QtWidgets.QCheckBox('Show the YAML tab (advanced)')
        self.show_yaml.setChecked(self.settings().value('show_yaml', False, type=bool))
        self.show_yaml.toggled.connect(lambda on: (self.settings().setValue('show_yaml', on),
                                                   self.set_yaml_visible(on)))
        general.full(self.show_yaml)
        ynote = QtWidgets.QLabel('Off (default): edit with the forms. On: a YAML tab shows the character\'s working '
                                 'copy in the plan format; typing there updates the forms, and Savegame ▸ Save '
                                 'writes it. It is tied to this savegame; Recipe ▸ Save as recipe makes a '
                                 'portable copy.')
        ynote.setObjectName('CardSub')
        ynote.setWordWrap(True)
        general.full(ynote)
        lay.addWidget(general)
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    # start page (no plan open)
    def build_start_page(self):
        page = QtWidgets.QWidget()
        page.setObjectName('EditorHost')
        outer = QtWidgets.QVBoxLayout(page)
        outer.addStretch(1)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        card = Card('Alienation Savegame Editor')
        card.setFixedWidth(620)
        icon = QtWidgets.QLabel()
        icon.setPixmap(app_icon().pixmap(64, 64))
        card.head.insertWidget(0, icon)
        card.findChild(QtWidgets.QLabel, 'CardTitle').setStyleSheet('font-size: 22px; font-weight: 700;')
        intro = QtWidgets.QLabel('Edit the characters in an ALIENATION savegame: their weapons, equipment, armor '
                                 'sets, levels and resources.<br><br>'
                                 'Start with <b>Savegame ▸ Open</b> and choose a savegame folder (the one holding '
                                 '<code>savedata.dat</code>). Edit any character, then <b>Savegame ▸ Save</b> writes '
                                 'an edited copy to a folder you choose.<br><br>'
                                 '<b>Recipes</b> are saved sets of items and profile values you can apply to any '
                                 'character: see <b>Recipe ▸ Apply example</b> once a savegame is open.')
        intro.setTextFormat(Qt.RichText)
        intro.setObjectName('CardSub')
        intro.setWordWrap(True)
        card.full(intro)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        return page

    def show_start(self):
        """No savegame open: show the start page and disable everything that needs one."""
        self.has_doc = False
        self.doc = PlanDoc()
        self.central.setCurrentWidget(self.start_page)
        self.set_doc_actions(False)
        self.setWindowTitle('Alienation Savegame Editor')

    def close_doc(self):
        if self.has_doc and self.confirm_discard():
            self.show_start()

    def set_doc_actions(self, on):
        for a in self.doc_actions:
            a.setEnabled(on)
        self.update_write_actions()

    # layout
    def build_ui(self):
        self.central = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central)
        self.start_page = self.build_start_page()
        self.central.addWidget(self.start_page)
        split = QtWidgets.QSplitter()
        split.setHandleWidth(1)
        self.editor_area = split
        self.central.addWidget(split)

        side = QtWidgets.QWidget()
        side.setObjectName('Sidebar')
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(8)
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(4, 0, 4, 0)
        lab = QtWidgets.QLabel('CHARACTER')
        lab.setObjectName('SectionHeader')
        top.addWidget(lab)
        top.addStretch(1)
        sl.addLayout(top)
        self.slot_combo = SlotCombo()
        self.slot_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.slot_combo.setMinimumContentsLength(12)   # don't widen the sidebar to the longest summary
        self.slot_combo.currentIndexChanged.connect(self.slot_changed)
        self.slot_combo.setVisible(False)
        sl.addWidget(self.slot_combo)
        self.no_save = QtWidgets.QLabel('No savegame open. Use Savegame ▸ Open to edit a character.')
        self.no_save.setObjectName('Faint')
        self.no_save.setWordWrap(True)
        self.no_save.setContentsMargins(4, 0, 4, 0)
        sl.addWidget(self.no_save)
        sl.addWidget(hline())
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(KeepColourDelegate(self.tree))
        self.tree.setColumnCount(2)               # name (★ instead of the rarity dot when equipped) | check status
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QtCore.QSize(12, 12))
        self.tree.setTextElideMode(Qt.ElideMiddle)  # long names keep their end: the level and any #n
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(self.select_item)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        self.tree.itemDoubleClicked.connect(lambda it, _: self.equip_entry(it.data(0, Qt.UserRole)))
        sl.addWidget(self.tree, 1)
        split.addWidget(side)

        self.pages = QtWidgets.QStackedWidget()
        self.pages.setObjectName('EditorHost')
        self.editors = {
            'weapons': ItemEditor(self, 'weapons'),
            'equipment': ItemEditor(self, 'equipment'), 'armor_sets': ArmorEditor(self),
            'profile': ProfileEditor(self),
        }
        self.scrolls = {}
        for k, ed in self.editors.items():
            sc = QtWidgets.QScrollArea()
            sc.setObjectName('EditorScroll')
            sc.setWidgetResizable(True)
            ed.setObjectName('EditorHost')
            sc.setWidget(ed)
            sc.setFrameShape(QtWidgets.QFrame.NoFrame)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.pages.addWidget(sc)
            self.scrolls[k] = sc
            ed.changed.connect(self.model_changed)
        split.addWidget(self.pages)

        right = QtWidgets.QWidget()
        right.setObjectName('RightPanel')
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(0, 4, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        ywrap = QtWidgets.QWidget()
        yl = QtWidgets.QVBoxLayout(ywrap)
        yl.setContentsMargins(8, 8, 8, 8)
        self.yaml_error = QtWidgets.QLabel()
        self.yaml_error.setObjectName('Banner')
        self.yaml_error.setWordWrap(True)
        self.yaml_error.setVisible(False)
        yl.addWidget(self.yaml_error)
        self.yaml_view = QtWidgets.QPlainTextEdit()
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        font.setPointSize(12)
        self.yaml_view.setFont(font)
        self.yaml_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.yaml_view.setStyleSheet(f'QPlainTextEdit {{ background:{BG}; border:1px solid {BORDER}; border-radius:8px; padding:6px; }}')
        self.yaml_view.setTabChangesFocus(False)
        self.yaml_view.setPlaceholderText('The plan\'s YAML appears here as you add entries.\n\n'
                                          'You can also type or paste YAML here; it is applied as you type.')
        self.highlighter = YamlHighlighter(self.yaml_view.document())
        self.yaml_view.textChanged.connect(self.yaml_typed)
        self.setting_text = False
        yl.addWidget(self.yaml_view)
        self.tabs.addTab(ywrap, 'YAML')
        self.checks = QtWidgets.QListWidget()
        self.checks.setWordWrap(True)
        self.checks.setResizeMode(QtWidgets.QListView.Adjust)
        self.checks.setUniformItemSizes(False)
        self.checks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.checks.setSpacing(1)
        self.checks.itemActivated.connect(self.check_clicked)
        self.checks.itemClicked.connect(self.check_clicked)
        cw = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(cw)
        cl.setContentsMargins(8, 8, 8, 8)
        legend = QtWidgets.QLabel(level_legend())
        legend.setTextFormat(Qt.RichText)
        legend.setObjectName('Muted')
        legend.setToolTip('<qt>' + '<br>'.join(f'{LEVEL_GLYPH[k]} {v}' for k, v in LEVEL_MEANING.items()) + '</qt>')
        cl.addWidget(legend)
        cl.addWidget(self.checks)
        self.tabs.addTab(cw, 'Checks')
        chw = QtWidgets.QWidget()
        chl = QtWidgets.QVBoxLayout(chw)
        chl.setContentsMargins(8, 8, 8, 8)
        top = QtWidgets.QHBoxLayout()
        self.changes_label = QtWidgets.QLabel()
        self.changes_label.setObjectName('Muted')
        self.changes_label.setWordWrap(True)
        self.revert_btn = QtWidgets.QPushButton('Revert all changes…')
        self.revert_btn.setToolTip('Go back to the file as last saved (Undo brings the changes back)')
        self.revert_btn.clicked.connect(self.revert)
        top.addWidget(self.changes_label, 1)
        top.addWidget(self.revert_btn)
        chl.addLayout(top)
        self.diff_view = QtWidgets.QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(font)
        self.diff_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.diff_view.setStyleSheet(self.yaml_view.styleSheet())
        self.diff_hl = DiffHighlighter(self.diff_view.document())
        chl.addWidget(self.diff_view)
        self.tabs.addTab(chw, 'Changes')
        self.tabs.addTab(self.build_settings_tab(), 'Settings')
        self.set_yaml_visible(self.show_yaml.isChecked())
        rl.addWidget(self.tabs)
        self.collapse_btn = QtWidgets.QToolButton()
        self.collapse_btn.setText('»')
        self.collapse_btn.setToolTip('Collapse this panel to its tabs (⌘\\)')
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(lambda: self.set_right_collapsed(True))
        self.tabs.setCornerWidget(self.collapse_btn, Qt.TopRightCorner)
        self.expand_btn = QtWidgets.QToolButton()           # shown above the vertical tabs when collapsed
        self.expand_btn.setText('«')
        self.expand_btn.setToolTip('Expand this panel (⌘\\)')
        self.expand_btn.setCursor(Qt.PointingHandCursor)
        self.expand_btn.clicked.connect(lambda: self.set_right_collapsed(False))
        self.expand_btn.setVisible(False)
        rl.insertWidget(0, self.expand_btn, 0, Qt.AlignHCenter)
        self.tabs.tabBarClicked.connect(self.tab_clicked)
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+\\'), self,
                        activated=lambda: self.set_right_collapsed(not self.right_collapsed))
        self.right_panel, self.split = right, split
        self.right_collapsed = False
        split.addWidget(right)
        split.setSizes([280, 800, 400])
        for i, stretch in enumerate((0, 1, 0)):            # window resizes go to the editor, not the sidebars
            split.setStretchFactor(i, stretch)
        if self.settings().value('right_collapsed', False, type=bool):
            QtCore.QTimer.singleShot(0, lambda: self.set_right_collapsed(True))

        self.statusBar().hide()

    def build_menus(self):
        """Savegame and Recipe menus (also toolbar buttons), Edit and Help in the menu bar."""
        mb = self.menuBar()
        # Savegame: the document
        gm = mb.addMenu('&Savegame')
        self.act_open_save = gm.addAction('Open…', self.open_game_save, QtGui.QKeySequence.Open)
        self.save_recent_menu = gm.addMenu('Recent')
        self.save_recent_menu.aboutToShow.connect(lambda: self.fill_recent_saves(self.save_recent_menu))
        self.save_recent_menu.addAction('(none)').setEnabled(False)   # filled on show; non-empty so macOS keeps it
        gm.addSeparator()
        self.act_write = gm.addAction('Save', lambda: self.write_save(ask=False), QtGui.QKeySequence.Save)
        self.act_write_as = gm.addAction('Save as…', lambda: self.write_save(ask=True), QtGui.QKeySequence.SaveAs)
        gm.addSeparator()
        self.act_revert = gm.addAction('Revert…', self.revert_all)
        self.act_revert.setToolTip('Discard the unsaved edits to every character')
        self.act_close = gm.addAction('Close', self.close_savegame, QtGui.QKeySequence.Close)
        quit_ = gm.addAction('Quit', self.close, QtGui.QKeySequence.Quit)
        quit_.setMenuRole(QtGui.QAction.QuitRole)            # macOS moves it to the application menu
        self.savegame_menu = gm
        # Recipe: reusable sets of items and profile values
        rm = mb.addMenu('&Recipe')
        self.act_apply = rm.addAction('Apply recipe…', self.apply_recipe_dialog)
        self.act_apply.setToolTip('Add a recipe\'s items to this character and set its profile values')
        ex = rm.addMenu('Apply example')
        for name in sorted(os.listdir(EXAMPLES_DIR)):
            if name.endswith('.yaml'):
                ex.addAction(name, lambda n=name: self.apply_recipe(os.path.join(EXAMPLES_DIR, n)))
        rm.addSeparator()
        self.act_export = rm.addAction('Save as recipe…', self.save_recipe)
        self.act_export.setToolTip('Save some of this character\'s items and profile values as a reusable recipe')
        self.recipe_menu = rm
        # Edit
        e = mb.addMenu('&Edit')
        doc_acts = [self.act_write, self.act_write_as, self.act_revert, self.act_close, self.act_apply,
                    ex.menuAction(), self.act_export,
                    e.addAction('Undo', self.undo, QtGui.QKeySequence.Undo),
                    e.addAction('Redo', self.redo, QtGui.QKeySequence.Redo)]
        e.addSeparator()
        doc_acts += [e.addAction('Duplicate', self.duplicate, QtGui.QKeySequence('Ctrl+D'))]
        da = e.addAction('Delete item', self.delete)
        doc_acts.append(da)
        da.setShortcuts([QtGui.QKeySequence('Ctrl+Backspace'), QtGui.QKeySequence('Delete')])
        da.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.tree.addAction(da)
        e.addSeparator()
        doc_acts += [e.addAction('Show unsaved changes', lambda: self.tabs.setCurrentIndex(2),
                                 QtGui.QKeySequence('Ctrl+Shift+D')),
                     e.addAction('Revert this character…', self.revert)]
        self.doc_actions = doc_acts
        h = mb.addMenu('&Help')
        h.addAction('Help for the current field (F1)', self.field_help)
        h.addAction('Recipe format guide (docs/save-editor.md)',
                    lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(DOCS)))
        h.addAction('Example recipes folder', lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(EXAMPLES_DIR)))
        self.build_toolbar()

    def build_toolbar(self):
        """The Plan and Savegame menus as buttons, plus the character picker once a savegame is open."""
        tb = QtWidgets.QToolBar('Menus')
        tb.setObjectName('MainToolbar')
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, tb)
        for text, menu, tip in (('Savegame ▾', self.savegame_menu, 'Open, save and close savegames'),
                                ('Recipe ▾', self.recipe_menu, 'Apply saved sets of items to a character, or save '
                                                               'some as a recipe')):
            b = QtWidgets.QToolButton()
            b.setObjectName('TB')
            b.setText(text)
            b.setToolTip(tip)
            b.setMenu(menu)
            b.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            b.setCursor(Qt.PointingHandCursor)
            tb.addWidget(b)
        gap = QtWidgets.QWidget()
        gap.setFixedWidth(10)
        tb.addWidget(gap)
        grow = QtWidgets.QWidget()
        grow.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(grow)
        relaunch = QtWidgets.QToolButton()
        relaunch.setObjectName('TB')
        relaunch.setText('↻')
        relaunch.setToolTip('Relaunch the editor (picks up changes to its code); reopens this savegame and '
                            'character')
        relaunch.setCursor(Qt.PointingHandCursor)
        relaunch.clicked.connect(self.relaunch)
        tb.addWidget(relaunch)
        guide = QtWidgets.QToolButton()
        guide.setObjectName('TB')
        guide.setText('?')
        guide.setToolTip('Getting started')
        guide.setCursor(Qt.PointingHandCursor)
        guide.clicked.connect(lambda: self.show_guide(guide))
        tb.addWidget(guide)
        # Short messages ("Saved …") appear as a toast at the bottom right of the window.
        self.toast = QtWidgets.QLabel(self)
        self.toast.setStyleSheet(f'background:{CARD_HI}; color:{TEXT}; border:1px solid {TEAL}; '
                                 f'border-radius:8px; padding:8px 14px;')
        self.toast.hide()
        self.toast_timer = QtCore.QTimer(self, singleShot=True, timeout=self.toast.hide)

    def show_guide(self, anchor):
        """Getting started, as an overlay under the toolbar's ? button."""
        pop = QtWidgets.QFrame(self, Qt.Popup)
        pop.setObjectName('HelpPopup')
        pop.setAttribute(Qt.WA_DeleteOnClose)
        lay = QtWidgets.QVBoxLayout(pop)
        lay.setContentsMargins(18, 14, 18, 14)
        title = QtWidgets.QLabel('Getting started')
        title.setStyleSheet(f'font-weight:700; font-size:15px; color:{TEAL};')
        body = QtWidgets.QLabel(GUIDE_HTML)
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setFixedWidth(460)
        lay.addWidget(title)
        lay.addWidget(body)
        pop.adjustSize()
        corner = anchor.mapToGlobal(QtCore.QPoint(anchor.width(), anchor.height() + 6))
        pop.move(corner.x() - pop.width(), corner.y())
        pop.show()

    def flash(self, msg, ms=3500):
        """Show a short message in a toast at the bottom right of the window."""
        self.toast.setText(msg)
        self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 18, self.height() - self.toast.height() - 18)
        self.toast.raise_()
        self.toast.show()
        self.toast_timer.start(ms)

    # recent plans
    def settings(self):
        """Remembered settings (recent savegames, folders, panel state). SAVE_EDITOR_SETTINGS=<file.ini>
        points them at a separate file, so test runs never touch the user's own preferences."""
        path = os.environ.get('SAVE_EDITOR_SETTINGS')
        if path:
            return QtCore.QSettings(path, QtCore.QSettings.IniFormat)
        return QtCore.QSettings('alienation', 'save-editor')

    # documents: the savegame, with one working copy per edited character
    @staticmethod
    def doc_dirty(doc):
        return doc.text() != doc.saved_text

    @property
    def dirty(self):
        """Unsaved edits to any character of the open savegame."""
        return self.has_doc and any(self.doc_dirty(d) for d in self.char_docs.values())

    def confirm_discard(self):
        if not self.dirty:
            return True
        name = os.path.basename(os.path.normpath(self.session.path)) if self.session else 'the savegame'
        r = QtWidgets.QMessageBox.question(self, 'Unsaved changes', f'Save your changes to {name}?',
                                           QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard |
                                           QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Save:
            return self.write_save(ask=self.write_target is None)
        return r == QtWidgets.QMessageBox.Discard

    def character_doc(self, slot):
        """The working copy of a character: its whole inventory as a plan that rebuilds it in place."""
        if slot not in self.char_docs:
            doc = PlanDoc(text=core.plan_to_yaml(core.dump_plan(self.session.root, slot)))
            doc.saved_text = doc.text()
            doc.pending_name = f'slot {slot}'
            doc.history, doc.hpos, doc.last_push = [doc.text()], 0, (0, None)
            self.char_docs[slot] = doc
        return self.char_docs[slot]

    def switch_to(self, slot):
        """Show a character. Edits to the one we leave stay in memory until the savegame is saved."""
        if self.has_doc and self.doc is not None:
            self.doc.history, self.doc.hpos, self.doc.last_push = self.history, self.hpos, self.last_push
        self.slot = slot
        self.doc = self.character_doc(slot)
        self.history, self.hpos, self.last_push = self.doc.history, self.doc.hpos, self.doc.last_push
        self.has_doc = True
        self.central.setCurrentWidget(self.editor_area)
        self.set_doc_actions(True)
        self.remember_saved()
        self.update_slot_labels()
        self.update_inventory_widgets()
        self.rebuild_tree(select=('plan',))
        self.refresh()

    def update_slot_labels(self):
        """Character dropdown: a ● marks characters with unsaved edits."""
        for i in range(self.slot_combo.count()):
            sl = self.slot_combo.itemData(i)
            char = self.session.root['slots'][sl]
            mark = '● ' if sl in self.char_docs and self.doc_dirty(self.char_docs[sl]) else ''
            self.slot_combo.setItemData(i, mark + character_short(sl, char), SlotCombo.SHORT)
            self.slot_combo.setItemText(i, f'{mark}Slot {sl}: {core.character_summary(char)}')
        self.slot_combo.update()

    def remember_saved(self):
        try:
            self.saved_plain = yaml.safe_load(self.doc.saved_text) or {}
        except yaml.YAMLError:
            self.saved_plain = {}

    def entry_changed(self, section, i):
        """Has entry i changed since the last save? Entries for owned items are matched by the item they
        rebuild, so deleting or adding one doesn't mark the others; other entries by position."""
        def items(plain):
            v = plain.get(section) if isinstance(plain, dict) else None
            return [v] if isinstance(v, dict) else v or []

        def owned(e):
            ref = e.get('replace') if isinstance(e, dict) else None
            return ref.get('index') if isinstance(ref, dict) else ref

        now, before = items(self.current_plain), items(self.saved_plain)
        if i >= len(now):
            return False
        idx = owned(now[i])
        if idx is not None:
            return now[i] != next((e for e in before if owned(e) == idx), None)
        return i >= len(before) or now[i] != before[i]

    def update_changes(self):
        old, new = self.doc.saved_text, self.doc.text()
        if old == new:
            self.changes_label.setText('No unsaved changes to this character.')
            self.diff_view.setPlainText('')
            self.revert_btn.setEnabled(False)
            self.tabs.setTabText(2, 'Changes')
            return
        lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                          'as saved', 'now', n=2, lineterm=''))
        added = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
        removed = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
        self.changes_label.setText(f'<span style="color:#4ade80">+{added}</span> / '
                                   f'<span style="color:#f87171">−{removed}</span> lines since '
                                   f'the savegame was opened or last saved. '
                                   f'Changed entries are orange in the list.')
        bar = self.diff_view.verticalScrollBar().value()
        self.diff_view.setPlainText('\n'.join(lines))
        self.diff_view.verticalScrollBar().setValue(bar)
        self.revert_btn.setEnabled(True)
        self.tabs.setTabText(2, f'Changes ({added + removed})')

    def revert(self):
        """Edit ▸ Revert this character: back to how it was when opened or last saved (⌘Z undoes)."""
        if not self.doc_dirty(self.doc):
            return
        if QtWidgets.QMessageBox.question(self, 'Revert this character',
                                          'Discard the unsaved changes to this character?\n\n'
                                          'Edit ▸ Undo brings them back.') != QtWidgets.QMessageBox.Yes:
            return
        key = self.current_key()
        self.doc.data = self.doc.parse(self.doc.saved_text)
        self.last_push = (0, None)
        self.push_history()
        self.rebuild_tree(select=key)
        self.refresh()
        self.flash('Reverted this character')

    def revert_all(self):
        """Savegame ▸ Revert: discard the unsaved edits to every character."""
        if not self.dirty:
            return
        if QtWidgets.QMessageBox.question(self, 'Revert savegame',
                                          'Discard the unsaved changes to every character?') != QtWidgets.QMessageBox.Yes:
            return
        self.char_docs = {}
        self.has_doc = False
        self.switch_to(self.slot)
        self.flash('Reverted every character')

    def close_savegame(self):
        if not self.has_doc or not self.confirm_discard():
            return
        self.session = None
        self.slot = None
        self.char_docs = {}
        self.slot_combo.clear()
        self.slot_combo.setVisible(False)
        self.no_save.setVisible(True)
        self.show_start()

    def relaunch(self):
        """Restart the editor in this process (so the app's launcher keeps waiting on it), reopening the
        savegame, character and window position. Asks about unsaved changes only when quitting does."""
        if self.confirm_quit.isChecked() and not self.confirm_discard():
            return
        g = self.geometry()
        os.environ['SAVE_EDITOR_RELAUNCH'] = json.dumps({'slot': self.slot,
                                                         'geometry': [g.x(), g.y(), g.width(), g.height()]})
        self.settings().sync()
        args = [os.path.abspath(__file__)] + ([self.session.path] if self.session is not None else [])
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable] + args)

    def closeEvent(self, e):
        if not self.confirm_quit.isChecked() or self.confirm_discard():
            e.accept()
        else:
            e.ignore()

    # sidebar
    def rebuild_tree(self, select=None):
        if select is None:
            select = self.current_key()
        self.tree.blockSignals(True)
        self.tree.clear()
        bold = QtGui.QFont()
        bold.setBold(True)
        plan = QtWidgets.QTreeWidgetItem(['Profile', ''])
        plan.setData(0, Qt.UserRole, ('plan',))
        plan.setFont(0, bold)
        self.tree.addTopLevelItem(plan)
        plan.setFirstColumnSpanned(True)           # no check status: those are in the Checks tab
        heads = []
        self.add_buttons, self.head_labels = {}, {}
        self._tree_layout = self.tree_layout()
        for group in self.tree_groups():
            section, cat = group
            members = [i for i, spec in enumerate(self.doc.entries(section))
                       if section != 'weapons' or self.weapon_group(spec) == cat]
            if cat == 'unknown' and not members:
                continue                            # only shown while a weapon has no valid type
            head = QtWidgets.QTreeWidgetItem(['', ''])
            head.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(head)
            heads.append((head, group))
            for i in members:
                it = QtWidgets.QTreeWidgetItem(head, ['', ''])
                it.setData(0, Qt.UserRole, (section, i))
            head.setExpanded(True)
            if not members:
                empty = QtWidgets.QTreeWidgetItem(head, ['none', ''])
                empty.setFlags(Qt.NoItemFlags)
                empty.setForeground(0, QtGui.QColor(FAINT))
        for head, group in heads:
            head.setFirstColumnSpanned(True)
            self.tree.setItemWidget(head, 0, self.section_heading(*group))
        self.update_add_buttons()
        self.tree.blockSignals(False)
        self.update_tree_labels()
        self.select_key(select)

    @staticmethod
    def tree_groups():
        """Sidebar groups: weapons split by slot type (as the game caps them), then equipment and armor sets."""
        return [('weapons', 'primary'), ('weapons', 'secondary'), ('weapons', 'heavy'), ('weapons', 'unknown'),
                ('equipment', None), ('armor_sets', None)]

    @staticmethod
    def weapon_group(spec):
        return (core.WEAPON_CATEGORY.get(spec.get('code')) if isinstance(spec, dict) else None) or 'unknown'

    def tree_layout(self):
        """What decides the sidebar's grouping; the tree is rebuilt when it changes (e.g. a weapon's type)."""
        return tuple(self.weapon_group(e) for e in self.doc.entries('weapons'))

    def group_count(self, section, cat):
        entries = self.doc.entries(section)
        return sum(1 for e in entries if self.weapon_group(e) == cat) if section == 'weapons' else len(entries)

    @staticmethod
    def group_cap(section, cat):
        return {'weapons': core.MAX_PER_CATEGORY, 'equipment': core.MAX_EQUIPMENT,
                'armor_sets': core.MAX_ARMOR_SETS}[section] if cat != 'unknown' else None

    def group_title(self, section, cat):
        n, cap = self.group_count(section, cat), self.group_cap(section, cat)
        name = f'WEAPONS: {cat.upper()} TYPE' if cat == 'unknown' else \
            f'WEAPONS: {cat.upper()}' if section == 'weapons' else SECTION_TITLES[section].upper()
        return f'{name} ({n}/{cap})' if cap else name

    def section_heading(self, section, cat=None):
        """A sidebar heading ('WEAPONS: PRIMARY (3/10)') with its own + Add button."""
        w = QtWidgets.QWidget()
        l = QtWidgets.QHBoxLayout(w)
        l.setContentsMargins(0, 0, 2, 0)
        l.setSpacing(4)
        lab = QtWidgets.QLabel(self.group_title(section, cat))
        lab.setObjectName('SectionHeader')
        lab.setStyleSheet('letter-spacing: 0.5px;')      # the longest, 'WEAPONS: SECONDARY (10/10)', fits
        self.head_labels[section, cat] = lab
        l.addWidget(lab)
        l.addStretch(1)
        if cat == 'unknown':
            return w
        add = QtWidgets.QToolButton()
        add.setText('＋')
        add.setCursor(Qt.PointingHandCursor)
        add.setStyleSheet(f'QToolButton {{ color:{ACCENT}; font-weight:600; font-size: 15px; padding: 0 4px; }}'
                          f'QToolButton:disabled {{ color:{FAINT}; }}')
        add.setFixedWidth(22)
        add.clicked.connect(lambda: self.add_new(section, cat))
        self.add_buttons[section, cat] = add
        l.addWidget(add)
        return w

    def add_new(self, section, cat=None):
        """Heading ＋ Add: a fresh item. A new primary is the character's own class primary."""
        if section == 'weapons':
            code = {'heavy': 'machine_gun', 'secondary': 'shotgun'}.get(cat)
            if cat == 'primary':
                code = 'smg'
                if self.session is not None and self.slot is not None:
                    armor = self.session.root['slots'][self.slot]['inventory']['armor']['code']
                    code = core.CLASS_PRIMARY.get(armor, code)
            return self.add(section, new_weapon(code))
        self.add(section, new_equipment() if section == 'equipment' else new_armor_set())

    def update_add_buttons(self):
        """Refresh each heading's count and disable its ＋ Add when that group is full (the game refuses an 11th)."""
        if not getattr(self, 'add_buttons', None):
            return
        for (section, cat), lab in self.head_labels.items():
            lab.setText(self.group_title(section, cat))
        for (section, cat), b in self.add_buttons.items():
            cap = self.group_cap(section, cat)
            full = self.group_count(section, cat) >= cap
            what = {'weapons': f'{cat} weapon', 'equipment': 'equipment item', 'armor_sets': 'armor set'}[section]
            if section == 'armor_sets':             # over 10 loads fine; the game just stops adding looted sets
                b.setToolTip(f'Add a new {what}' + (f' (at {cap} or more the game gives you no new looted sets)'
                                                     if full else ''))
                continue
            b.setEnabled(not full)
            b.setToolTip(f'Full: the game holds at most {cap} of these' if full else f'Add a new {what}')

    def items(self):
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            yield it.value()
            it += 1

    def update_tree_labels(self):
        names = {sec: self.item_names(sec) for sec in ('weapons', 'equipment', 'armor_sets')}
        for it in self.items():
            key = it.data(0, Qt.UserRole)
            if not key:
                continue
            if key == ('plan',):
                changed = (self.current_plain or {}).get('profile') != (self.saved_plain or {}).get('profile')
                it.setText(0, 'Profile')
                it.setForeground(0, QtGui.QColor(ACCENT if changed else TEXT))
                it.setToolTip(0, 'Levels, keys, credits, Xenoflowers, cores and metals')
            if len(key) == 2:
                section, i = key
                entries = self.doc.entries(section)
                if i >= len(entries):
                    continue
                spec = entries[i]
                r = spec.get('rarity', 'legendary' if section != 'armor_sets' else 1) if isinstance(spec, dict) else 0
                ri = core.RARITIES.index(r) if r in core.RARITIES else r if isinstance(r, int) and 0 <= r <= 4 else 0
                equipped = isinstance(spec, dict) and bool(spec.get('equip'))
                changed = self.entry_changed(section, i)       # new or edited: shown by the orange name
                it.setText(0, names[section][i])
                it.setIcon(0, (star_icon if equipped else dot_icon)(RARITY_COLOURS[ri]))
                it.setData(0, BADGE_ROLE, armor_colours(spec) if section == 'armor_sets' else None)
                it.setForeground(0, QtGui.QColor(ACCENT if changed else TEXT))
            if key == ('plan',):                   # character-wide checks are only listed in the Checks tab
                continue
            rep = self.reports.get(key)
            level = rep.worst() if rep else None
            level = level if level in ('error', 'untested', 'warning') else ('ok' if len(key) == 2 else None)
            # An icon, not text: the selection style would repaint text in the plain text colour.
            it.setIcon(1, glyph_icon(LEVEL_GLYPH[level], LEVEL_COLOURS[level]) if level else QtGui.QIcon())
            lines = rep.lines() if rep and rep.messages() else []
            if len(key) == 2 and isinstance(spec, dict) and spec.get('equip'):
                lines = ['★ Equipped'] + lines
            it.setToolTip(0, '\n'.join(lines))
            it.setToolTip(1, '\n'.join(rep.lines()) if rep and rep.messages() else '')

    def current_key(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else ('plan',)

    def select_key(self, key):
        for it in self.items():
            if it.data(0, Qt.UserRole) == key:
                self.tree.setCurrentItem(it)
                return
        for it in self.items():
            if it.data(0, Qt.UserRole) == ('plan',):
                self.tree.setCurrentItem(it)
                return

    def select_item(self, it, _prev=None):
        if not it:
            return
        key = it.data(0, Qt.UserRole)
        if not key:
            return
        self.show_editor(key)

    def show_editor(self, key):
        kind = 'profile' if key[0] == 'plan' else key[0]     # the plan's name row opens the profile
        ed = self.editors[kind]
        if kind == 'profile':
            m = self.doc.data.get(kind)
            if not isinstance(m, dict):
                m = CommentedMap()       # attached to the document on first edit
            ed.bind(m)
        else:
            entries = self.doc.entries(kind)
            if key[1] >= len(entries) or not isinstance(entries[key[1]], dict):
                return
            ed.bind(entries[key[1]], kind, key[1])
        self.pages.setCurrentWidget(self.scrolls[kind])
        self.update_inventory_widgets()

    def tree_menu(self, pos):
        it = self.tree.itemAt(pos)
        key = it.data(0, Qt.UserRole) if it else None
        if not (key and len(key) == 2):
            return
        menu = QtWidgets.QMenu(self)
        spec = self.doc.entries(key[0])[key[1]]
        eq = menu.addAction('Wear' if key[0] == 'armor_sets' else 'Equip', lambda: self.equip_entry(key))
        eq.setEnabled(not (isinstance(spec, dict) and spec.get('equip')))
        menu.addAction('Duplicate', self.duplicate)
        menu.addSeparator()
        act = menu.addAction('Delete', lambda: self.delete_entry(key))
        if isinstance(spec, dict) and spec.get('equip'):
            act.setEnabled(False)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def add(self, section, entry):
        self.doc.entries(section, create=True).append(entry)
        self.rebuild_tree(select=(section, len(self.doc.entries(section)) - 1))
        self.model_changed()

    def removals(self):
        """[(section, item index, expected code or None, position in the remove list)] of the plan."""
        rem = self.doc.data.get('remove')
        out = []
        if isinstance(rem, dict):
            for section in ('weapons', 'equipment', 'armor_sets'):
                refs = rem.get(section) or []
                for pos, r in enumerate(refs if isinstance(refs, list) else [refs]):
                    idx = r.get('index') if isinstance(r, dict) else r
                    if isinstance(idx, int):
                        out.append((section, idx, r.get('code') if isinstance(r, dict) else None, pos))
        return out

    def add_removal(self, section, idx, code):
        rem = self.doc.section_map('remove', create=True)
        refs = rem.get(section)
        if not isinstance(refs, list):
            refs = flow_seq([])
            set_key(rem, section, refs, KEY_ORDER['remove'])
        if any(s == section and i == idx for s, i, _, _ in self.removals()):
            return
        refs.append(flow_map([('index', idx), ('code', code)]) if code else idx)

    def delete_entry(self, key):
        """Delete an entry. An item you own becomes a deletion from the savegame; a new item just goes."""
        section, i = key
        entries = self.doc.entries(section)
        spec = entries[i]
        if isinstance(spec, dict) and spec.get('equip'):
            self.flash(equipped_delete_hint(section, spec), 5000)
            return
        ref = spec.get('replace') if isinstance(spec, dict) else None
        idx = ref.get('index') if isinstance(ref, dict) else ref
        label = core.entry_label(section, spec, ITEM_NAMES)
        del entries[i]
        if isinstance(idx, int):
            self.add_removal(section, idx, ref.get('code') if isinstance(ref, dict) else None)
            msg = f'Deleted {label} from the savegame (when it is saved). ⌘Z undoes it.'
        else:
            msg = f'Removed the new {label}'
        self.doc.prune()
        self.rebuild_tree(select=('plan',))
        self.model_changed()
        self.flash(msg, 5000)

    def equip_entry(self, key):
        """Sidebar double-click / Equip: equip the item (wear the armor set), as ticking its Equip box does;
        whatever held that slot is unequipped."""
        if not (isinstance(key, tuple) and len(key) == 2):
            return
        self.select_key(key)
        flags = self.editors[key[0]].flags
        if not flags.equip.isChecked():
            flags.equip.setChecked(True)

    def duplicate(self):
        key = self.current_key()
        if len(key) != 2:
            return
        entries = self.doc.entries(key[0])
        dup = copy.deepcopy(entries[key[1]])
        del_key(dup, 'replace')
        del_key(dup, 'equip')
        entries.append(dup)                        # new items go at the end, as in the savegame
        self.rebuild_tree(select=(key[0], len(entries) - 1))
        self.model_changed()

    def delete(self):
        key = self.current_key()
        if len(key) == 2:
            return self.delete_entry(key)

    # model <-> text
    def model_changed(self):
        self.push_history()
        self.refresh()

    def push_history(self):
        text = self.doc.text()
        if self.history and self.history[self.hpos] == text:
            return
        now, key = time.monotonic(), self.current_key()
        del self.history[self.hpos + 1:]
        if now - self.last_push[0] < 0.8 and self.last_push[1] == key and self.hpos > 0:
            self.history[self.hpos] = text           # coalesce quick edits of one field
        else:
            self.history.append(text)
            self.hpos = len(self.history) - 1
        self.last_push = (now, key)

    def undo(self):
        if self.yaml_view.hasFocus():
            self.yaml_view.undo()
            return
        if self.hpos > 0:
            self.hpos -= 1
            self.restore(self.history[self.hpos])

    def redo(self):
        if self.yaml_view.hasFocus():
            self.yaml_view.redo()
            return
        if self.hpos < len(self.history) - 1:
            self.hpos += 1
            self.restore(self.history[self.hpos])

    def restore(self, text):
        key = self.current_key()
        self.doc.data = self.doc.parse(text)
        self.last_push = (0, None)
        self.rebuild_tree(select=key)
        self.refresh()

    def refresh(self, text=True):
        if text:
            t = self.doc.text()
            if t != self.yaml_view.toPlainText():
                bar = self.yaml_view.verticalScrollBar().value()
                self.setting_text = True
                self.yaml_view.setPlainText(t)
                self.setting_text = False
                self.yaml_view.verticalScrollBar().setValue(bar)
            self.yaml_error.setVisible(False)
        self.run_checks()
        self.update_changes()
        if self.tree_layout() != getattr(self, '_tree_layout', None):
            self.rebuild_tree()                    # e.g. a weapon's type moved it under another heading
        self.update_tree_labels()
        self.update_add_buttons()
        name = os.path.basename(os.path.normpath(self.session.path)) if self.session else ''
        self.setWindowTitle(f'{"● " if self.dirty else ""}{name} — Alienation Savegame Editor')
        if self.session is not None:
            self.update_slot_labels()


    def yaml_typed(self):
        if not self.setting_text:
            self.text_timer.start()

    def text_edited(self):
        text = self.yaml_view.toPlainText()
        try:
            data = self.doc.parse(text)
            core.parse_plan_text(text, self.doc.name)
        except Exception as e:
            self.yaml_error.setText(f'Not applied, the YAML has an error:\n{e}')
            self.yaml_error.setVisible(True)
            return
        key = self.current_key()
        self.doc.data = data
        self.push_history()
        self.rebuild_tree(select=key)
        self.yaml_error.setVisible(False)
        self.refresh(text=False)

    # checks
    def run_checks(self):
        allow = self.untested.isChecked()
        try:
            docs = core.parse_plan_text(self.doc.text(), self.doc.name)
        except core.PlanError as e:
            self.reports = {'plan': core.Report(allow)}
            self.reports['plan'].error(str(e))
            docs = []
        self.current_plain = docs[0] if docs else {}
        if docs:
            self.reports = core.check_document(docs[0], self.doc.name, allow)
        elif 'plan' not in self.reports or not self.reports['plan'].errors:
            self.reports = {}
        self.save_check = None                 # stale until the savegame check reruns
        self.update_write_actions()
        self.show_checks()
        if self.session is not None and self.slot is not None:
            self.save_check_timer.start()

    def current_texts(self):
        return tuple((sl, d.text()) for sl, d in sorted(self.char_docs.items()))

    def run_save_check(self):
        """Apply every edited character (and the one shown) to the savegame in memory. Saving is only
        allowed when all of them pass."""
        if not (self.has_doc and self.session is not None and self.slot is not None):
            return
        allow = self.untested.isChecked()
        plans, reports = {}, {}
        for sl, doc in self.char_docs.items():
            if sl != self.slot and not self.doc_dirty(doc):
                continue
            try:
                plans[sl], _ = core.merge_plans([(doc.name, d) for d in core.parse_plan_text(doc.text(), doc.name)])
            except core.PlanError as e:
                reports[sl] = core.Report(allow)
                reports[sl].error(str(e))
        data = None
        if plans:
            r, data = self.session.apply_each(plans, allow)
            reports.update(r)
        if any(rep.failed() for rep in reports.values()):
            data = None
        self.save_check = (self.current_texts(), reports, data)
        self.update_write_actions()
        self.show_checks()

    def show_checks(self):
        extra = None
        if self.session is not None and self.slot is not None:
            title = f'slot {self.slot}'
            rep = core.Report(self.untested.isChecked())
            if self.save_check is None:
                rep.note('checking…')
            else:
                # Show what the savegame adds: drop the file name and repeats of the plan checks.
                # Also drop notes about items the user hasn't touched: every owned item is rebuilt in
                # place, so "replaced"/"equipped" for an unchanged one says nothing.
                seen = {m for r in self.reports.values() for _, m in r.messages()}
                prefix = f'{self.doc.name} '
                untouched = {sec: {e['replace'].get('index') if isinstance(e['replace'], dict) else e['replace']
                                   for i, e in enumerate(self.doc.entries(sec))
                                   if isinstance(e, dict) and e.get('replace') is not None
                                   and not self.entry_changed(sec, i)}
                             for sec in ('weapons', 'equipment', 'armor_sets')}
                mine = self.save_check[1].get(self.slot)
                for level, msg in (mine.messages() if mine else []):
                    msg = msg.replace(prefix, '')
                    if msg in seen:
                        continue
                    m = re.match(r'(weapons|equipment|armor_sets)\[(\d+)\] (replaced|equipped)', msg)
                    if level == 'note' and m and int(m.group(2)) in untouched[m.group(1)]:
                        continue
                    {'note': rep.notes, 'warning': rep.warnings, 'error': rep.errors,
                     'untested': rep.untested}[level].append(msg)
                for sl, other in self.save_check[1].items():
                    if sl != self.slot and other.failed():
                        rep.errors.append(f'slot {sl} has problems too: pick it in CHARACTER to see them')
            extra = (title, {'save': rep})
        self.fill_checks(self.reports, extra)

    def can_write(self):
        """The savegame may only be saved when every edited character passes its checks."""
        return (self.has_doc and self.session is not None and self.save_check is not None
                and self.save_check[2] is not None and self.save_check[0] == self.current_texts())

    def update_write_actions(self):
        ok = self.can_write()
        for a in (self.act_write, self.act_write_as):
            a.setEnabled(ok)
        why = ('' if ok else
               'Open a plan first' if not self.has_doc else
               'Open a savegame first' if self.session is None else
               'Fix the problems in the Checks tab first')
        for a in (self.act_write, self.act_write_as):
            a.setToolTip(why or 'Apply the plan and write an edited copy of the savegame')
        # macOS menus don't show tooltips, so say why in the menu itself when the checks block saving
        blocked = (not ok and self.has_doc and self.session is not None and self.save_check is not None
                   and self.save_check[0] == self.current_texts())
        self.act_write.setText('Save (fix the problems in Checks first)' if blocked else 'Save')
        self.act_write_as.setText('Save as… (fix the problems in Checks first)' if blocked else 'Save as…')

    def item_names(self, section):
        """The sidebar names of a section's items. Items sharing a name are numbered #1, #2, … in sidebar
        order (weapons by type group), so the sidebar and the Checks tab can tell them apart."""
        entries = self.doc.entries(section)
        base = [core.entry_label(section, e, ITEM_NAMES) for e in entries]
        if section == 'armor_sets':             # 'armor set, looted, 2 effects' → 'Looted set' (+ colour badge)
            base = [short_armor_name(b) for b in base]
        if section == 'weapons':
            rank = {grp: n for n, grp in enumerate(self.tree_groups())}
            order = sorted(range(len(entries)), key=lambda i: (rank[('weapons', self.weapon_group(entries[i]))], i))
        else:
            order = range(len(entries))
        names, seen = list(base), {}
        for i in order:
            if base.count(base[i]) > 1:
                seen[base[i]] = seen.get(base[i], 0) + 1
                names[i] = f'{base[i]} #{seen[base[i]]}'
        return names

    def saved_item_ref(self, section, idx):
        """(sidebar key or None, name) for the savegame's item idx. Items beyond the savegame's list are
        the new ones, added at the end in sidebar order."""
        entries = self.doc.entries(section)
        for i, e in enumerate(entries):
            r = e.get('replace') if isinstance(e, dict) else None
            if (r.get('index') if isinstance(r, dict) else r) == idx:
                return (section, i), self.item_names(section)[i]
        inv = self.session.root['slots'][self.slot]['inventory'] if self.session and self.slot is not None else {}
        lst = inv.get({'weapons': 'weapons', 'equipment': 'items', 'armor_sets': 'color_sets'}[section]) or []
        if idx < len(lst):                      # deleted from the sidebar: name it from the savegame
            dump = {'weapons': core.dump_weapon, 'equipment': core.dump_equipment,
                    'armor_sets': core.dump_armor_set}[section]
            name = core.entry_label(section, dump(lst[idx]), ITEM_NAMES)
            return None, short_armor_name(name) if section == 'armor_sets' else name
        new = [i for i, e in enumerate(entries) if isinstance(e, dict) and e.get('replace') is None]
        k = idx - len(lst)
        if 0 <= k < len(new):
            return (section, new[k]), self.item_names(section)[new[k]]
        return None, f'{section}[{idx}]'

    def describe_check(self, msg, key):
        """A check message in the sidebar's words: the item's name instead of 'weapons[3]' (the editor's
        own list position for most checks, the savegame's for what saving changes and deletions), and
        display names instead of codes. Returns (text, sidebar key to jump to)."""
        sections = r'(weapons|equipment|armor_sets)'
        m = re.match(sections + r'\[(\d+)\]:\s*', msg)
        if m:                                   # '<plan position>: …' from the item's own checks
            section, i = m.group(1), int(m.group(2))
            entries = self.doc.entries(section)
            if i < len(entries):
                key = (section, i)
                msg = f'{self.item_names(section)[i]}: {msg[m.end():]}'
        else:
            msg = re.sub(r'^remove\.\w+:\s*', '', msg)
            msg = re.sub(r'^armor set (\d+) ', lambda a: f'armor_sets[{a.group(1)}] ', msg)
            m = re.search(sections + r'\[(\d+)\]', msg)
            if m and self.session is not None:  # savegame positions
                k, name = self.saved_item_ref(m.group(1), int(m.group(2)))
                msg = msg[:m.start()] + name + msg[m.end():]
                key = k or key
        head, sep, rest = msg.partition(': ')
        rest = rest if sep else head
        if sep and isinstance(key, tuple):      # 'Xeno Rifle legendary L25: xenorifle is …' → ': another …'
            spec = self.doc.entries(key[0])[key[1]] if key[1] < len(self.doc.entries(key[0])) else None
            code = spec.get('code') if isinstance(spec, dict) else None
            if code and re.match(rf'{code}\b', rest):
                rest = re.sub(rf'^{code}\s+(is\s+)?', '', rest)
        for code, name in ITEM_NAMES.items():
            rest = re.sub(rf'\b{code}\b', name, rest)
        return (head + sep + rest) if sep else rest, key

    def fill_checks(self, reports, extra=None):
        """List the plan checks and the savegame check by severity: errors, refused untested values,
        warnings, then (muted, last) what saving will change. Items are named as in the sidebar and
        listed in its order, character-wide checks first."""
        self.checks.clear()
        by_level = {'error': [], 'untested': [], 'warning': [], 'note': []}
        groups = [(None, reports)] + ([extra] if extra else [])
        for gtitle, reps in groups:
            for key, rep in reps.items():
                for level, msg in rep.messages():
                    if level == 'note' and gtitle is None:
                        continue                       # plan notes repeat what the savegame check says
                    shown = msg[len('untested: '):] if msg.startswith('untested: ') else msg
                    shown, k = self.describe_check(shown, key)
                    if shown not in [t for t, _ in by_level[level]]:
                        by_level[level].append((shown, k))
        order = {it.data(0, Qt.UserRole): n for n, it in enumerate(self.items())}
        for level in by_level:
            by_level[level].sort(key=lambda tk: order.get(tk[1], -1) if isinstance(tk[1], tuple) else -1)
        counts = {lv: len(v) for lv, v in by_level.items()}
        headings = {'error': 'Errors', 'untested': 'Untested values', 'warning': 'Warnings',
                    'note': 'What saving changes' + (f' ({extra[0]})' if extra else '')}

        def heading(text):
            g = QtWidgets.QListWidgetItem(text)
            f = QtGui.QFont()
            f.setBold(True)
            g.setFont(f)
            g.setFlags(Qt.ItemIsEnabled)
            self.checks.addItem(g)

        if not any(counts[lv] for lv in ('error', 'untested', 'warning')):
            it = QtWidgets.QListWidgetItem(f'{LEVEL_GLYPH["ok"]}  No problems found')
            it.setForeground(QtGui.QColor(LEVEL_COLOURS['ok']))
            self.checks.addItem(it)
        for level in ('error', 'untested', 'warning', 'note'):
            if not by_level[level]:
                continue
            heading(f'{headings[level]} ({counts[level]})' if level != 'note' else headings[level])
            for shown, key in by_level[level]:
                it = QtWidgets.QListWidgetItem(f'{LEVEL_GLYPH[level]}  {shown}')
                it.setForeground(QtGui.QColor(LEVEL_COLOURS[level]))
                it.setData(Qt.UserRole, key)
                it.setToolTip(LEVEL_MEANING.get(level, 'What happens when the savegame is saved'))
                self.checks.addItem(it)
        parts = []
        for level in ('error', 'untested', 'warning'):
            if counts.get(level):
                parts.append(f'{counts[level]} {"refused (untested)" if level == "untested" else level + "s" if counts[level] != 1 else level}')
        n = sum(counts.get(k, 0) for k in ('error', 'untested', 'warning'))
        worst = next((lv for lv in ('error', 'untested', 'warning') if counts.get(lv)), None)
        self.tabs.setTabText(1, f'Checks ({n})' if worst else 'Checks')
        self.tabs.setTabIcon(1, glyph_icon(LEVEL_GLYPH[worst], LEVEL_COLOURS[worst]) if worst else QtGui.QIcon())
        self.tabs.setTabToolTip(1, ', '.join(parts) if parts else 'All plan checks pass')

    def check_clicked(self, it):
        key = it.data(Qt.UserRole)
        if isinstance(key, tuple):
            self.select_key(key)
        elif key in ('profile', 'target', 'plan', 'remove'):
            self.select_key(('plan',))

    # save context
    def pick_save_folder(self, path=None, quiet=False):
        """Open a savegame folder (asking for one unless path is given); returns a SaveSession or None."""
        if path is None:
            start = self.settings().value('save_dir', '') or ''
            if not os.path.isdir(start):
                start = os.path.join(ROOT, 'savegames')
            path = QtWidgets.QFileDialog.getExistingDirectory(self, 'Choose a savegame folder (with savedata.dat)',
                                                              start)
            if not path:
                return None
        if not os.path.exists(os.path.join(path, 'savedata.dat')):
            if not quiet:
                QtWidgets.QMessageBox.warning(self, 'No savegame there', f'{path} has no savedata.dat')
            return None
        try:
            session = core.SaveSession(path)
        except Exception as e:
            if not quiet:
                QtWidgets.QMessageBox.warning(self, 'Cannot read savegame', str(e))
            return None
        self.settings().setValue('save_dir', os.path.dirname(os.path.abspath(path)))
        rec = [os.path.abspath(path)] + [x for x in self.recent_saves() if x != os.path.abspath(path)]
        self.settings().setValue('recent_saves', rec[:10])
        return session

    def last_save(self):
        """The savegame opened most recently, whether or not it still exists."""
        v = self.settings().value('recent_saves', []) or []
        v = [v] if isinstance(v, str) else list(v)
        return v[0] if v else None

    def recent_saves(self):
        v = self.settings().value('recent_saves', []) or []
        v = [v] if isinstance(v, str) else list(v)
        return [p for p in v if os.path.exists(os.path.join(p, 'savedata.dat'))]

    def fill_recent_saves(self, menu):
        menu.clear()
        rec = self.recent_saves()
        for p in rec:
            menu.addAction(display_path(p), lambda p=p: self.open_game_save(p))
        if not rec:
            menu.addAction('No recent savegames yet').setEnabled(False)

    def attach_session(self, session, slot=None):
        """Use this savegame for item pickers, checks and saving; select a character slot."""
        self.session = session
        self.write_target = None             # Savegame ▸ Save asks where the first time
        self.slot_combo.blockSignals(True)
        self.slot_combo.clear()
        for sl, c in self.session.characters():
            self.slot_combo.addItem(f'Slot {sl}: {core.character_summary(c)}', sl)
            self.slot_combo.setItemData(self.slot_combo.count() - 1, character_short(sl, c), SlotCombo.SHORT)
        self.slot_combo.blockSignals(False)
        self.slot_combo.setVisible(True)
        self.no_save.setVisible(False)
        i = self.slot_combo.findData(slot)
        self.slot_combo.blockSignals(True)
        self.slot_combo.setCurrentIndex(max(i, 0))
        self.slot_combo.blockSignals(False)
        self.slot = self.slot_combo.currentData()
        self.slot_combo.setToolTip(f'Characters in {display_path(session.path)}')

    def open_game_save(self, path=None, quiet=False):
        """Savegame ▸ Open: show the first character (slot 0 when there is one); switch with CHARACTER.
        quiet (opening the last savegame on launch): problems just leave the start page showing."""
        if not self.confirm_discard():
            return
        session = self.pick_save_folder(path, quiet)
        if not session:
            return
        slots = [sl for sl, _ in session.characters()]
        if not slots:
            if not quiet:
                QtWidgets.QMessageBox.warning(self, 'No characters', 'That savegame has no characters.')
            return
        self.char_docs = {}
        self.has_doc = False
        self.doc = None
        self.attach_session(session, 0 if 0 in slots else slots[0])
        self.switch_to(self.slot)

    def slot_changed(self, *_):
        """CHARACTER dropdown: show that character; unsaved edits to the others are kept."""
        new = self.slot_combo.currentData()
        if self.session and new is not None and new != self.slot:
            self.switch_to(new)

    def inventory_by_section(self):
        if not self.session or self.slot is None:
            return {}
        out = {}
        for section, idx, code, text, mark in core.inventory_rows(self.session.root['slots'][self.slot]):
            out.setdefault(section, []).append((idx, code, text, mark))
        return out

    def update_inventory_widgets(self):
        inv = self.inventory_by_section()
        pass

    def write_save(self, ask=True):
        """Savegame ▸ Save / Save as: apply the plan and write an edited copy of the savegame."""
        self.run_save_check()
        if not self.can_write():
            bad = sorted(sl for sl, r in (self.save_check[1] if self.save_check else {}).items() if r.failed())
            QtWidgets.QMessageBox.warning(self, 'Not saved', 'Some changes have problems (character slot '
                                          f'{", ".join(map(str, bad)) or "?"}); see the Checks tab.')
            self.tabs.setCurrentIndex(1)
            return False
        data = self.save_check[2]
        out = None if ask else self.write_target
        if out is None:
            start = self.settings().value('write_dir', '') or ''
            if not os.path.isdir(start):
                start = os.path.join(ROOT, 'edits') if os.path.isdir(os.path.join(ROOT, 'edits')) else ROOT
            chosen = QtWidgets.QFileDialog.getExistingDirectory(
                self, 'Choose where to put the edited savegame (e.g. a folder on a USB drive)', start)
            if not chosen:
                return False
            # The console expects the savegame in a folder named like the original (CUSA04181_sdimg_savedata).
            name = os.path.basename(os.path.normpath(self.session.folder)) if self.session.folder else None
            out = chosen if not name or os.path.basename(os.path.normpath(chosen)) == name else os.path.join(chosen, name)
            try:
                check_output_path(os.path.join(out, 'savedata.dat'), [self.session.file])
            except OutputPathError:
                QtWidgets.QMessageBox.warning(self, 'Not saved', 'That is the savegame you opened; saving there '
                                              'would overwrite it. Choose another folder.')
                return False
            if os.path.exists(os.path.join(out, 'savedata.dat')):   # only ask when something would be replaced
                box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, 'Replace savegame?',
                                            f'{out} already holds a savegame. Replace it with this one?',
                                            QtWidgets.QMessageBox.Cancel, self)
                replace = box.addButton('Replace', QtWidgets.QMessageBox.AcceptRole)
                box.exec()
                if box.clickedButton() is not replace:
                    return False
            self.settings().setValue('write_dir', chosen)
        try:
            written = self.session.write(data, out)
        except OutputPathError as e:
            QtWidgets.QMessageBox.warning(self, 'Not saved', str(e))
            return False
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Save failed', str(e))
            return False
        self.write_target = out
        for doc in self.char_docs.values():           # unsaved changes now count from this save
            doc.saved_text = doc.text()
        self.remember_saved()
        self.rebuild_tree()
        self.refresh(text=False)
        self.flash(f'Saved the savegame to {display_path(out)}')
        return True

    # recipes
    def apply_recipe_dialog(self):
        start = self.settings().value('recipe_dir', '') or EXAMPLES_DIR
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Apply a recipe', start, 'Recipes (*.yaml *.yml)')
        if p:
            self.settings().setValue('recipe_dir', os.path.dirname(p))
            self.apply_recipe(p)

    def apply_recipe(self, path):
        """Add a recipe's items to this character and set its profile values. Parts tied to item numbers in
        some savegame (replace / remove) can't carry over: replaced items are added as new ones and
        removals are skipped."""
        try:
            recipe = PlanDoc(path).data
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Cannot read recipe', f'{path}\n\n{e}')
            return
        added, as_new, skipped, unequipped = {}, 0, 0, []
        for section in ('weapons', 'equipment', 'armor_sets'):
            entries = recipe.get(section) or []
            for e in [entries] if isinstance(entries, dict) else entries:
                if not isinstance(e, dict):
                    continue
                e = strip_comments(copy.deepcopy(e))
                if 'replace' in e:
                    del e['replace']
                    as_new += 1
                mine = self.doc.entries(section, create=True)
                if e.get('equip'):                   # each slot holds one item: the recipe's takes it
                    slot = equip_slot(section, e)
                    for x in mine:
                        if isinstance(x, dict) and x.get('equip') and equip_slot(section, x) == slot:
                            del_key(x, 'equip')
                            unequipped.append(core.entry_label(section, x, ITEM_NAMES))
                mine.append(e)
                added[section] = added.get(section, 0) + 1
        rem = recipe.get('remove')
        if isinstance(rem, dict):
            skipped = sum(len(v) if isinstance(v, list) else 1 for v in rem.values())
        prof_keys = []
        prof = recipe.get('profile')
        if isinstance(prof, dict) and prof:
            mine = self.doc.section_map('profile', create=True)
            for k, v in prof.items():
                if isinstance(v, dict) and isinstance(mine.get(k), dict):
                    for kk, vv in v.items():
                        mine[k][kk] = strip_comments(copy.deepcopy(vv))
                else:
                    set_key(mine, k, strip_comments(copy.deepcopy(v)), KEY_ORDER['profile'])
                prof_keys.append(str(k))
        self.doc.prune()
        self.rebuild_tree(select=('plan',))
        self.model_changed()
        parts = [f'{n} {SECTION_TITLES[s].lower() if n != 1 else SECTION_TITLES[s].lower().rstrip("s")}'
                 for s, n in added.items()]
        msg = f'Applied {os.path.basename(path)}: ' + (', '.join(parts) or 'no items')
        if prof_keys:
            msg += f'; profile {", ".join(prof_keys)}'
        if as_new:
            msg += f'. {as_new} item(s) that replaced owned items were added as new'
        if skipped:
            msg += f'. {skipped} deletion(s) by item number were skipped'
        if unequipped:
            msg += f'. Unequipped {", ".join(unequipped)} to make room'
        self.flash(msg, 7000)

    def save_recipe(self):
        """Save the ticked items and/or profile values (changed ones pre-ticked), as they are now, as a
        portable recipe: no savegame item numbers, so it applies to any character."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('Save as recipe')
        dlg.setMinimumWidth(560)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.addWidget(QtWidgets.QLabel('What to include, as it is now (changed ones are ticked):'))
        lst = QtWidgets.QListWidget()
        lst.setStyleSheet(f'QListWidget {{ background:{BG}; border:1px solid {BORDER}; border-radius:7px; padding:4px; }}')
        prof_now = (self.current_plain or {}).get('profile') or {}
        if prof_now:
            it = QtWidgets.QListWidgetItem('Profile values: ' + ', '.join(map(str, prof_now)))
            it.setData(Qt.UserRole, ('profile', None))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            changed = prof_now != ((self.saved_plain or {}).get('profile') or {})
            it.setCheckState(Qt.Checked if changed else Qt.Unchecked)
            lst.addItem(it)
        for section in ('weapons', 'equipment', 'armor_sets'):
            for i, e in enumerate(self.doc.entries(section)):
                if not isinstance(e, dict):
                    continue
                it = QtWidgets.QListWidgetItem(f'{SECTION_TITLES[section]}: {core.entry_label(section, e, ITEM_NAMES)}')
                it.setData(Qt.UserRole, (section, i))
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if (e.get('replace') is None or self.entry_changed(section, i))
                                 else Qt.Unchecked)
                lst.addItem(it)
        lay.addWidget(lst)
        if prof_now:
            note = QtWidgets.QLabel('Profile values are only the ones this editor sets (levels, keys, cores, metals, '
                                    'credits, Xenoflowers). The rest of the savegame\'s profile, such as unlocks and '
                                    'game progress, isn\'t part of a recipe.')
            note.setObjectName('Muted')
            note.setWordWrap(True)
            lay.addWidget(note)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.button(QtWidgets.QDialogButtonBox.Ok).setText('Save…')
        btns.button(QtWidgets.QDialogButtonBox.Ok).setObjectName('Primary')
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        recipe = CommentedMap()
        for i in range(lst.count()):
            it = lst.item(i)
            if it.checkState() != Qt.Checked:
                continue
            section, idx = it.data(Qt.UserRole)
            if section == 'profile':
                recipe['profile'] = copy.deepcopy(self.doc.data.get('profile'))
                continue
            e = copy.deepcopy(self.doc.entries(section)[idx])
            for k in ('replace', 'equip'):
                if k in e:
                    del e[k]
            recipe.setdefault(section, CommentedSeq()).append(e)
        if not recipe:
            self.flash('Nothing selected, so no recipe was saved')
            return
        folder = self.settings().value('recipe_dir', '') or os.path.join(ROOT, 'recipes')
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save recipe', os.path.join(folder, 'my_recipe.yaml'),
                                                     'Recipes (*.yaml *.yml)')
        if not p:
            return
        if not p.endswith(('.yaml', '.yml')):
            p += '.yaml'
        doc = PlanDoc()
        doc.data = recipe
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        with open(p, 'w') as f:
            f.write(f'# Recipe saved from {os.path.basename(os.path.normpath(self.session.path))}, slot {self.slot}.\n'
                    f'# Apply it to any character with Recipe ▸ Apply recipe (or save-editor-cli.py apply).\n'
                    + doc.text())
        self.settings().setValue('recipe_dir', os.path.dirname(p))
        self.flash(f'Saved recipe {display_path(p)}')

    # help
    def field_help(self):
        w = QtWidgets.QApplication.focusWidget()
        while w is not None and not w.property('help_key'):
            w = w.parentWidget()
        if w is None:
            self.flash('Click into a field first, or use its ? button')
            return
        show_help(w, w.property('help_title') or 'Help', w.property('help_key'))


def main():
    QtWidgets.QApplication.setApplicationName('Alienation Savegame Editor')
    app = QtWidgets.QApplication(sys.argv)
    apply_theme(app)
    args = [a for a in sys.argv[1:] if not a.startswith('-psn_')]   # Finder's process serial number
    win = MainWindow(args[0] if args else None)
    state = os.environ.pop('SAVE_EDITOR_RELAUNCH', None)      # set by MainWindow.relaunch
    if state:
        state = json.loads(state)
        win.setGeometry(*state['geometry'])
        if state.get('slot') is not None and win.slot_combo.findData(state['slot']) >= 0:
            win.slot_combo.setCurrentIndex(win.slot_combo.findData(state['slot']))
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
