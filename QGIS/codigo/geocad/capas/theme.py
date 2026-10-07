# -*- coding: utf-8 -*-
"""Hojas de estilo inspiradas en los temas oscuro y claro de AutoCAD."""

THEMES = {
    'dark': {
        'bg': '#3b4453', 'panel': '#2b313c', 'alt': '#323946', 'header': '#4a5466',
        'border': '#20252d', 'text': '#e6e9ee', 'muted': '#9aa5b1', 'sel': '#3d6a99',
        'hover': '#46536a', 'input': '#262b34', 'accent': '#4ea3ff', 'current': '#59d65f',
    },
    'light': {
        'bg': '#e8eaee', 'panel': '#ffffff', 'alt': '#f4f6f9', 'header': '#d9dde4',
        'border': '#b9c0ca', 'text': '#1e2329', 'muted': '#5d6773', 'sel': '#bcd5f0',
        'hover': '#e3edf8', 'input': '#ffffff', 'accent': '#1f6fc4', 'current': '#1d8f27',
    },
}


def palette(name):
    return THEMES.get(name, THEMES['dark'])


def stylesheet(name):
    c = palette(name)
    return """
QWidget#CadLayerRoot, QDialog#CadDialog {{ background: {bg}; color: {text}; }}
QWidget#CadLayerRoot QLabel, QDialog#CadDialog QLabel, QDialog#CadDialog QCheckBox,
QWidget#CadLayerRoot QCheckBox {{ color: {text}; background: transparent; }}
QLabel#CadTitle {{ font-weight: bold; }}
QLabel#CadMuted {{ color: {muted}; }}
QToolBar#CadPaletteBar {{ background: {bg}; border: none; spacing: 1px; padding: 2px; }}
QToolBar#CadPaletteBar QToolButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 2px; padding: 3px; color: {text}; }}
QToolBar#CadPaletteBar QToolButton:hover {{ background: {hover}; border-color: {border}; }}
QToolBar#CadPaletteBar QToolButton:pressed, QToolBar#CadPaletteBar QToolButton:checked {{ background: {sel}; }}
QToolBar#CadPaletteBar::separator {{ background: {border}; width: 1px; margin: 3px 4px; }}
QLineEdit#CadSearch, QDialog#CadDialog QLineEdit, QDialog#CadDialog QSpinBox, QDialog#CadDialog QDoubleSpinBox,
QDialog#CadDialog QComboBox {{
    background: {input}; color: {text}; border: 1px solid {border}; border-radius: 2px; padding: 2px 4px;
    selection-background-color: {sel}; }}
QTableWidget#CadGrid, QTreeWidget#CadFilters, QListWidget#CadList, QTreeWidget#CadList {{
    background: {panel}; alternate-background-color: {alt}; color: {text};
    border: 1px solid {border}; gridline-color: {border};
    selection-background-color: {sel}; selection-color: {text}; outline: 0; }}
QTableWidget#CadGrid::item, QTreeWidget#CadFilters::item, QListWidget#CadList::item, QTreeWidget#CadList::item {{
    padding: 0px 3px; border: none; }}
QTableWidget#CadGrid::item:hover, QTreeWidget#CadFilters::item:hover, QListWidget#CadList::item:hover,
QTreeWidget#CadList::item:hover {{ background: {hover}; }}
QTableWidget#CadGrid::item:selected, QTreeWidget#CadFilters::item:selected, QListWidget#CadList::item:selected,
QTreeWidget#CadList::item:selected {{ background: {sel}; }}
QHeaderView::section {{ background: {header}; color: {text}; border: none;
    border-right: 1px solid {border}; border-bottom: 1px solid {border}; padding: 3px 5px; }}
QTableCornerButton::section {{ background: {header}; border: none; }}
QSplitter::handle {{ background: {border}; }}
QDialog#CadDialog QPushButton, QWidget#CadLayerRoot QPushButton {{
    background: {header}; color: {text}; border: 1px solid {border}; border-radius: 2px; padding: 4px 14px; }}
QDialog#CadDialog QPushButton:hover, QWidget#CadLayerRoot QPushButton:hover {{ background: {hover}; }}
QDialog#CadDialog QPushButton:default {{ border-color: {accent}; }}
QDialog#CadDialog QTabWidget::pane {{ border: 1px solid {border}; background: {bg}; }}
QDialog#CadDialog QTabBar::tab {{ background: {header}; color: {text}; padding: 5px 14px; border: 1px solid {border}; }}
QDialog#CadDialog QTabBar::tab:selected {{ background: {bg}; border-bottom-color: {bg}; }}
QFrame#CadStatus {{ background: {header}; border-top: 1px solid {border}; }}
QGroupBox {{ color: {text}; border: 1px solid {border}; margin-top: 8px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 3px; }}
""".format(**c)
