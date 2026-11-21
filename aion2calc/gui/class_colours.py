"""The class colours' panel (0.2.466), as combat-review.js ``settings`` draws it: class colours on or off, a palette applied
with **Apply**, a colour for each class, and **Reset class colors**. ``saved`` gives what was chosen, ``{}`` once reset;
the caller keeps it (``/api/ui``'s ``combat_colors``).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from . import combat_records as cr
from . import combat_review as cw
from .chrome import FlowLayout
from .combat_saved import _button, _label


class ClassColours(QWidget):
    """Class colours on or off, a palette, a colour for each class, and Reset (``A2CombatReview.settings``)."""

    saved = Signal(dict)

    def __init__(self, preference: dict, parent: QWidget | None = None, ask_colour=None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.ask_colour = ask_colour or (lambda start, words: QColorDialog.getColor(QColor(start), self, words))
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.enabled = QCheckBox(cw.USE_CLASS_COLOURS)
        column.addWidget(self.enabled)
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(_label("Palette", wrap=False))
        self.palette = QComboBox()
        self.palette.setAccessibleName("Palette")
        self.palette.addItem(cw.CHOOSE_PALETTE, "")
        for name in cw.PALETTES:
            self.palette.addItem(name, name)
        line.addWidget(self.palette)
        line.addWidget(_button("Apply", self.apply))
        line.addStretch(1)
        column.addWidget(row)
        swatches = QWidget()
        swatches.setObjectName("plain")
        flow = FlowLayout(swatches, align=Qt.AlignLeft, gap=(12, 6))
        self.swatches: dict[str, QPushButton] = {}
        for cls in cr.CLASS_COLOURS:
            box = QWidget()
            box.setObjectName("plain")
            pair = QHBoxLayout(box)
            pair.setContentsMargins(0, 0, 0, 0)
            pair.setSpacing(6)
            pair.addWidget(_label(cls, wrap=False))
            swatch = QPushButton()
            swatch.setAccessibleName(f"{cls} colour")
            swatch.setFixedSize(44, 22)
            swatch.clicked.connect(lambda _checked=False, cls=cls: self._choose(cls))
            self.swatches[cls] = swatch
            pair.addWidget(swatch)
            flow.addWidget(box)
        column.addWidget(swatches)
        reset = QWidget()
        reset.setObjectName("plain")
        reset_line = QHBoxLayout(reset)
        reset_line.setContentsMargins(0, 0, 0, 0)
        reset_line.addWidget(_button(cw.RESET_COLOURS, self.reset))
        reset_line.addStretch(1)
        column.addWidget(reset)
        self.show_preference(preference)
        self.enabled.toggled.connect(lambda _on: self.save())       # any change but the palette's saves (``onchange``)

    def show_preference(self, preference: dict) -> None:
        """The panel as the preference reads: on unless turned off, each class in its colour."""
        self.enabled.blockSignals(True)
        self.enabled.setChecked(preference.get("enabled") is not False)
        self.enabled.blockSignals(False)
        self.colours = {cls: cr.class_colour(cls, {"colors": preference.get("colors") or {}}) for cls in cr.CLASS_COLOURS}
        for cls, colour in self.colours.items():
            self._paint(cls, colour)

    def _paint(self, cls: str, colour: str) -> None:
        self.swatches[cls].setStyleSheet(f"QPushButton {{ background: {colour}; border: 1px solid #3a4150; border-radius: 3px; }}")
        self.swatches[cls].setToolTip(colour)

    def preference(self) -> dict:
        return {"enabled": self.enabled.isChecked(), "colors": dict(self.colours)}

    def save(self) -> None:
        self.saved.emit(self.preference())

    def _choose(self, cls: str) -> None:
        """A class's colour chosen (``input type="color"``): saved as it is chosen."""
        chosen = self.ask_colour(self.colours[cls], f"{cls} colour")
        if chosen is None or not chosen.isValid():
            return
        self.colours[cls] = chosen.name()
        self._paint(cls, self.colours[cls])
        self.save()

    def apply(self) -> None:
        """The palette chosen applied (``data-apply-palette``): class colours on, its colours set, then saved."""
        palette = cw.PALETTES.get(self.palette.currentData() or "")
        if not palette:
            return
        self.enabled.blockSignals(True)
        self.enabled.setChecked(True)
        self.enabled.blockSignals(False)
        for cls, colour in palette.items():
            if cls in self.colours:
                self.colours[cls] = colour
                self._paint(cls, colour)
        self.save()

    def reset(self) -> None:
        """The class colours as the review's own (``data-reset``): nothing kept."""
        self.show_preference({})
        self.saved.emit({})
