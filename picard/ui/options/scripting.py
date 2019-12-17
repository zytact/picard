# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
# Copyright (C) 2006 Lukáš Lalinský
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

from PyQt5 import (
    QtCore,
    QtGui,
    QtWidgets,
)

from picard import config
from picard.const import (
    DEFAULT_NUMBERED_SCRIPT_NAME,
    DEFAULT_SCRIPT_NAME,
    PICARD_URLS,
)
from picard.script import ScriptParser
from picard.util import restore_method

from picard.ui import HashableListWidgetItem
from picard.ui.options import (
    OptionsCheckError,
    OptionsPage,
    register_options_page,
)
from picard.ui.ui_options_script import Ui_ScriptingOptionsPage


class TaggerScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):

    def __init__(self, document):
        super().__init__(document)
        self.func_re = QtCore.QRegExp(r"\$(?!noop)[a-zA-Z][_a-zA-Z0-9]*\(")
        self.func_fmt = QtGui.QTextCharFormat()
        self.func_fmt.setFontWeight(QtGui.QFont.Bold)
        self.func_fmt.setForeground(QtCore.Qt.blue)
        self.var_re = QtCore.QRegExp(r"%[_a-zA-Z0-9:]*%")
        self.var_fmt = QtGui.QTextCharFormat()
        self.var_fmt.setForeground(QtCore.Qt.darkCyan)
        self.escape_re = QtCore.QRegExp(r"\\.")
        self.escape_fmt = QtGui.QTextCharFormat()
        self.escape_fmt.setForeground(QtCore.Qt.darkRed)
        self.special_re = QtCore.QRegExp(r"[^\\][(),]")
        self.special_fmt = QtGui.QTextCharFormat()
        self.special_fmt.setForeground(QtCore.Qt.blue)
        self.bracket_re = QtCore.QRegExp(r"[()]")
        self.noop_re = QtCore.QRegExp(r"\$noop\(")
        self.noop_fmt = QtGui.QTextCharFormat()
        self.noop_fmt.setFontWeight(QtGui.QFont.Bold)
        self.noop_fmt.setFontItalic(True)
        self.noop_fmt.setForeground(QtCore.Qt.darkGray)
        self.rules = [
            (self.func_re, self.func_fmt, 0, -1),
            (self.var_re, self.var_fmt, 0, 0),
            (self.escape_re, self.escape_fmt, 0, 0),
            (self.special_re, self.special_fmt, 1, -1),
        ]

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)

        for expr, fmt, a, b in self.rules:
            index = expr.indexIn(text)
            while index >= 0:
                length = expr.matchedLength()
                self.setFormat(index + a, length + b, fmt)
                index = expr.indexIn(text, index + length + b)

        # Ignore everything if we're already in a noop function
        index = self.noop_re.indexIn(text) if self.previousBlockState() <= 0 else 0
        open_brackets = self.previousBlockState() if self.previousBlockState() > 0 else 0
        while index >= 0:
            next_index = self.bracket_re.indexIn(text, index)

            # Skip escaped brackets
            if (next_index > 0) and text[next_index - 1] == '\\':
                next_index += 1

            if (next_index > -1) and text[next_index] == '(':
                open_brackets += 1
            elif (next_index > -1) and text[next_index] == ')':
                open_brackets -= 1

            if next_index > -1:
                self.setFormat(index, next_index - index + 1, self.noop_fmt)
            elif (next_index == -1) and (open_brackets > 0):
                self.setFormat(index, len(text) - index, self.noop_fmt)

            # Check for next noop operation, necessary for multiple noops in one line
            if open_brackets == 0:
                next_index = self.noop_re.indexIn(text, next_index)

            index = next_index + 1 if (next_index > -1) and (next_index < len(text)) else -1

        self.setCurrentBlockState(open_brackets)


class ScriptListWidgetItem(HashableListWidgetItem):
    """Holds a script's list and text widget properties"""

    def __init__(self, name=None, enabled=True, script=""):
        super().__init__(name)
        self.setFlags(self.flags() | QtCore.Qt.ItemIsUserCheckable)
        if name is None:
            name = _(DEFAULT_SCRIPT_NAME)
        self.setText(name)
        self.setCheckState(QtCore.Qt.Checked if enabled else QtCore.Qt.Unchecked)
        self.script = script

    @property
    def pos(self):
        return self.listWidget().row(self)

    @property
    def name(self):
        return self.text()

    @property
    def enabled(self):
        return self.checkState() == QtCore.Qt.Checked

    def get_all(self):
        # tuples used to get pickle dump of settings to work
        return (self.pos, self.name, self.enabled, self.script)


class ScriptingOptionsPage(OptionsPage):

    NAME = "scripting"
    TITLE = N_("Scripting")
    PARENT = None
    SORT_ORDER = 85
    ACTIVE = True

    options = [
        config.BoolOption("setting", "enable_tagger_scripts", False),
        config.ListOption("setting", "list_of_scripts", []),
        config.IntOption("persist", "last_selected_script_pos", 0),
        config.Option("persist", "scripting_splitter", QtCore.QByteArray()),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_ScriptingOptionsPage()
        self.ui.setupUi(self)
        self.highlighter = TaggerScriptSyntaxHighlighter(self.ui.tagger_script.document())
        self.ui.tagger_script.setEnabled(False)
        self.ui.script_name.setEnabled(False)
        self.last_selected_script_pos = 0
        self.ui.splitter.setStretchFactor(0, 1)
        self.ui.splitter.setStretchFactor(1, 2)
        self.delete_shortcut = QtWidgets.QShortcut(self.ui.script_list)
        self.delete_shortcut.setKey(QtGui.QKeySequence.Delete)
        self.delete_shortcut.activated.connect(self.delete_selected_script)
        font = QtGui.QFont('Monospace')
        font.setStyleHint(QtGui.QFont.TypeWriter)
        self.ui.tagger_script.setFont(font)

    def delete_selected_script(self):
        indexes = self.ui.script_list.selectedIndexes()
        if indexes:
            self.remove_from_list_of_scripts(indexes[0].row())

    def rename_selected_script(self):
        items = self.ui.script_list.selectedItems()
        if items:
            self.rename_script(items[0])

    def move_selected_script_up(self):
        indexes = self.ui.script_list.selectedIndexes()
        if indexes:
            row = indexes[0].row()
            self.move_script(row, 1)
            new_index = self.ui.script_list.model().index(row - 1, 0)
            selection = self.ui.script_list.selectionModel()
            selection.select(new_index, QtCore.QItemSelectionModel.Clear | QtCore.QItemSelectionModel.SelectCurrent)

    def move_selected_script_down(self):
        indexes = self.ui.script_list.selectedIndexes()
        if indexes:
            row = indexes[0].row()
            self.move_script(row, -1)
            new_index = self.ui.script_list.model().index(row + 1, 0)
            selection = self.ui.script_list.selectionModel()
            selection.select(new_index, QtCore.QItemSelectionModel.Clear | QtCore.QItemSelectionModel.SelectCurrent)

    def script_name_changed(self):
        items = self.ui.script_list.selectedItems()
        if items:
            script = items[0]
            script.setText(self.ui.script_name.text())

    def script_selected(self):
        items = self.ui.script_list.selectedItems()
        if items:
            self.ui.tagger_script.setEnabled(True)
            self.ui.script_name.setEnabled(True)
            script = items[0]
            self.ui.tagger_script.setText(script.script)
            self.ui.script_name.setText(script.name)
            self.last_selected_script_pos = script.pos

    def rename_script(self, item):
        item.setSelected(True)
        self.ui.script_name.setFocus()
        self.ui.script_name.selectAll()

    def add_script(self):
        count = self.ui.script_list.count()
        numbered_name = _(DEFAULT_NUMBERED_SCRIPT_NAME) % (count + 1)

        list_item = ScriptListWidgetItem(name=numbered_name)
        list_item.setCheckState(QtCore.Qt.Checked)
        self.ui.script_list.addItem(list_item)
        list_item.setSelected(True)

    def remove_from_list_of_scripts(self, row):
        item = self.ui.script_list.item(row)
        confirm_remove = QtWidgets.QMessageBox()
        msg = _("Are you sure you want to remove this script?")
        reply = confirm_remove.question(confirm_remove, _('Confirm Remove'), msg, QtWidgets.QMessageBox.Yes,
                                        QtWidgets.QMessageBox.No)
        if item and reply == QtWidgets.QMessageBox.Yes:
            item = self.ui.script_list.takeItem(row)
            item = None
            if not self.ui.script_list:
                self.ui.tagger_script.setText("")
                self.ui.tagger_script.setEnabled(False)
                self.ui.script_name.setText("")
                self.ui.script_name.setEnabled(False)

            # update position of last_selected_script
            if row == self.last_selected_script_pos:
                self.last_selected_script_pos = 0
                # workaround to remove residue on UI
                if not self.ui.script_list.selectedItems():
                    current_item = self.ui.script_list.currentItem()
                    if current_item:
                        current_item.setSelected(True)
                    else:
                        item = self.ui.script_list.item(0)
                        if item:
                            item.setSelected(True)
            elif row < self.last_selected_script_pos:
                self.last_selected_script_pos -= 1

    def move_script(self, row, step):
        item1 = self.ui.script_list.item(row)
        item2 = self.ui.script_list.item(row - step)
        if item1 and item2:
            list_item = self.ui.script_list.takeItem(row)
            self.ui.script_list.insertItem(row - step, list_item)

    def live_update_and_check(self):
        items = self.ui.script_list.selectedItems()
        if items:
            script = items[0]
            script.script = self.ui.tagger_script.toPlainText()
        self.ui.script_error.setStyleSheet("")
        self.ui.script_error.setText("")
        try:
            self.check()
        except OptionsCheckError as e:
            self.ui.script_error.setStyleSheet(self.STYLESHEET_ERROR)
            self.ui.script_error.setText(e.info)
            return

    def check(self):
        parser = ScriptParser()
        try:
            parser.eval(self.ui.tagger_script.toPlainText())
        except Exception as e:
            raise OptionsCheckError(_("Script Error"), str(e))

    def restore_defaults(self):
        # Remove existing scripts
        self.ui.script_list.clear()
        self.ui.script_name.setText("")
        self.ui.tagger_script.setText("")
        super().restore_defaults()

    def load(self):
        self.ui.enable_tagger_scripts.setChecked(config.setting["enable_tagger_scripts"])
        for pos, name, enabled, text in config.setting["list_of_scripts"]:
            list_item = ScriptListWidgetItem(name, enabled, text)
            self.ui.script_list.addItem(list_item)

        # Select the last selected script item
        self.last_selected_script_pos = config.persist["last_selected_script_pos"]
        last_selected_script = self.ui.script_list.item(self.last_selected_script_pos)
        if last_selected_script:
            last_selected_script.setSelected(True)

        self.restore_state()

        args = {
            "picard-doc-scripting-url": PICARD_URLS['doc_scripting'],
        }
        text = _('<a href="%(picard-doc-scripting-url)s">Open Scripting'
                 ' Documentation in your browser</a>') % args
        self.ui.scripting_doc_link.setText(text)

    def _all_scripts(self):
        for row in range(0, self.ui.script_list.count()):
            item = self.ui.script_list.item(row)
            yield item.get_all()

    @restore_method
    def restore_state(self):
        # Preserve previous splitter position
        self.ui.splitter.restoreState(config.persist["scripting_splitter"])

    def save(self):
        config.setting["enable_tagger_scripts"] = self.ui.enable_tagger_scripts.isChecked()
        config.setting["list_of_scripts"] = list(self._all_scripts())
        config.persist["last_selected_script_pos"] = self.last_selected_script_pos
        config.persist["scripting_splitter"] = self.ui.splitter.saveState()

    def display_error(self, error):
        pass


register_options_page(ScriptingOptionsPage)
