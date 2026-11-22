"""My Uploads and My Character Identities in the native Combat Logs page (0.2.452), as log-ownership.js and
identity.js draw them.

- **My uploads:** the private credentials of the logs this computer uploaded (kept by the app, never in a log), each
  refreshed with its original server to show its visibility and link, its visibility changed (public once asked), its
  private link replaced, a moderation hold appealed, its log reviewed (read with its credential, since 0.2.474), the
  upload deleted, or the credential forgotten. Filters by title or ID, server and the visibility last seen;
  twenty-five to a page. Credentials can be exported to a private backup, imported from one, or recovered one at a
  time with an older upload's delete token.
- **My Character Identities:** the characters your public recordings on the share server can claim (three where you
  were the recording player), each claimed, renewed, recovered or challenged with newer recordings, released, hidden in
  other uploaders' public logs, or appealed after a revocation. Claims are proven by the credentials above and the
  identity credential the server issues is kept by the app; the requests go to the share server itself, as the web
  page sends them, never following a redirect with a credential.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from . import combat as cb
from . import theme
from .api import AppApi, why
from .combat_saved import Section, _button, _clear, _label, _row
from .result_windows import GridTable
from .results import _dict, _list, _truthy, js_text

#: How long an app request may take: the app asks the log server for an upload's state within 30 s.
TIMEOUT = 60


class Tasks(QObject):
    """Work off the interface's thread, one at a time in the order asked: each task is a function, its answer coming
    back as ``done(name, answer)``, or ``failed(name, why)`` when it raises."""

    done = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gui-task")

    def run(self, name: str, work) -> None:
        try:
            self._pool.submit(self._do, name, work)
        except RuntimeError:                     # stopped: its page has closed
            pass

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _do(self, name: str, work) -> None:
        try:
            answer = work()
        except Exception as exc:                 # noqa: BLE001 - any failure is said where the task was asked
            try:
                self.failed.emit(name, why(exc))
            except RuntimeError:
                pass
            return
        try:
            self.done.emit(name, answer)
        except RuntimeError:                     # its page has gone meanwhile
            pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """An identity credential is never sent on to wherever a redirect points (``redirect: 'error'``)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def identity_call(base: str, path: str, method: str = "GET", body: dict | None = None, token: str | None = None,
                  timeout: float = 30) -> dict:
    """One request to the share server's identity routes (identity.js ``call``): its answer, or ValueError with the
    server's reason."""
    headers = {"User-Agent": "aion2calc", "Cache-Control": "no-store"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["X-Identity-Token"] = token
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(base + path, data, headers, method=method), timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            out = json.loads(exc.read() or b"{}")
        except (OSError, ValueError):
            out = {}
        message = out.get("error") if isinstance(out, dict) else None
        raise ValueError(js_text(message) if message else f"Identity request failed ({exc.code})") from None
    try:
        out = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def _ask(parent: QWidget, words: str) -> bool:
    return QMessageBox.question(parent, "Combat logs", words) == QMessageBox.Yes


def _rich(text: str, name: str = "") -> QLabel:
    label = _label(text, name, rich=True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    return label


def _cell(spacing: int = 4) -> tuple[QWidget, QVBoxLayout]:
    """A table cell across its column, its parts kept together in the middle of the row (``vertical-align: middle``);
    ``_close`` ends it."""
    cell = QWidget()
    cell.setObjectName("plain")
    cell.setProperty("fill", True)
    column = QVBoxLayout(cell)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(spacing)
    column.addStretch(1)
    return cell, column


def _close(column: QVBoxLayout) -> None:
    column.addStretch(1)


class WrapCheck(QWidget):
    """A tick box whose words wrap in their column (a ``label`` around an ``input type="checkbox"``)."""

    def __init__(self, words: str, checked: bool, enabled: bool, toggled, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.box = QCheckBox()
        self.box.setAccessibleName(words)
        self.box.setChecked(checked)
        self.box.setEnabled(enabled)
        self.box.toggled.connect(toggled)
        self.words = _label(words)
        self.words.setEnabled(enabled)
        line.addWidget(self.box, 0, Qt.AlignTop)
        line.addWidget(self.words, 1)

    def mousePressEvent(self, event) -> None:           # its words tick it too
        if self.box.isEnabled():
            self.box.toggle()
        super().mousePressEvent(event)


def _note_box(text: str) -> QFrame:
    """A note inside a row (``p.note``)."""
    box = QFrame()
    box.setObjectName("rowNote")
    line = QVBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(_rich(text))
    return box


class _Appeal(Section):
    """An appeal folded under its title (``details``): why a moderator should look again, and Send appeal."""

    def __init__(self, title: str, send, enabled: bool = True, parent: QWidget | None = None):
        super().__init__(title, None, False, parent)
        self.body_layout.addWidget(_label("Why should a moderator look again? (10–1,000 characters; one appeal"
                                          + (" per hold)" if "hold" in title else ")"), "small"))
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Why should a moderator look again?")
        self.text.setFixedHeight(64)
        self.text.textChanged.connect(self._limit)
        self.body_layout.addWidget(self.text)
        self.body_layout.addWidget(_row(_button("Send appeal", lambda: send(self.text.toPlainText().strip()), enabled=enabled)))

    def _limit(self) -> None:
        text = self.text.toPlainText()
        if len(text) > 1000:                                    # ``maxlength="1000"``
            self.text.setPlainText(text[:1000])


class OwnedUploads(QFrame):
    """My Uploads (log-ownership.js). ``open_log`` reviews an upload's log, as its server gave it to the upload's
    credential (``io.open``): without it no upload has a Review, as the web page draws none without ``io.open``.
    ``open_link`` opens a shared link in the browser; ``confirm``, ``choose_file`` and ``save_file`` stand in for the
    questions and the file dialogs."""

    def __init__(self, api: AppApi | None, open_log=None, open_link=None, confirm=None, choose_file=None, save_file=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("note")
        self.api, self.open_log = api, open_log
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.confirm = confirm or (lambda words: _ask(self, words))
        self.choose_file = choose_file or self._ask_file
        self.save_file = save_file or self._ask_save
        self.tasks = Tasks(self) if api is not None else None
        if self.tasks is not None:
            self.tasks.done.connect(self._done)
            self.tasks.failed.connect(self._failed)
        self.rows: list[dict] = []
        self.status: dict[str, dict] = {}
        self.f = {"q": "", "server": "", "visibility": ""}
        self.page, self.message, self.busy, self.problem = 0, "", False, None
        self.acting: tuple[str, str] | None = None             # the upload and the action under way
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.fold = Section("My uploads · 0 saved credentials", None, True)
        layout.addWidget(self.fold)
        body = self.fold.body_layout
        body.addWidget(_label(cb.OWNED_NOTE, "small"))
        self.tools = [_button("Export private credentials", self.export_backup),
                      _button("Import private backup…", self.import_backup),
                      _button("Reload saved credentials", self.load)]
        body.addWidget(_row(*self.tools))
        body.addWidget(_label(cb.OWNED_BACKUP_NOTE, "small"))
        self.recover_fold = Section(cb.RECOVER_TITLE, None, False)
        self.recover_server = QLineEdit()
        self.recover_server.setPlaceholderText("Original server URL")
        self.recover_server.setAccessibleName("Original upload server")
        self.recover_id = QLineEdit()
        self.recover_id.setPlaceholderText("Upload ID")
        self.recover_id.setAccessibleName("Upload ID")
        self.recover_token = QLineEdit()
        self.recover_token.setEchoMode(QLineEdit.Password)
        self.recover_token.setPlaceholderText("Original delete token")
        self.recover_token.setAccessibleName("Original delete credential")
        self.recover_save = _button("Save credential locally", self.recover)
        self.recover_fold.body_layout.addWidget(_row(self.recover_server, self.recover_id, self.recover_token,
                                                     self.recover_save))
        body.addWidget(self.recover_fold)
        self.said = _label("")
        self.said.setAccessibleName("My uploads status")
        body.addWidget(self.said)
        holder = QWidget()
        holder.setObjectName("plain")
        self.list_box = QVBoxLayout(holder)
        self.list_box.setContentsMargins(0, 0, 0, 0)
        self.list_box.setSpacing(6)
        body.addWidget(holder)
        self.table_box: QVBoxLayout | None = None
        self.counted: QLabel | None = None
        self.load()

    def stop(self) -> None:
        if self.tasks is not None:
            self.tasks.stop()

    def _run(self, name: str, work) -> None:
        if self.tasks is not None:
            self.tasks.run(name, work)

    def _post(self, body: dict):
        return self.api.post("/api/log-ownership", body, timeout=TIMEOUT)

    def _say(self, words: str) -> None:
        """Words in the status line alone (``data-message``), the list as it is."""
        self.said.setText(words)

    # ---------------------------------------------------------------- reading
    def load(self) -> None:
        """The credentials the app keeps (``Reload saved credentials``)."""
        self._run("list", lambda: self.api.get("/api/log-ownership", timeout=TIMEOUT))

    def _done(self, name: str, answer) -> None:
        if name == "list":
            self.rows = [r for r in _list(answer) if isinstance(r, dict)]
            self.problem, self.busy = None, False
            self.render()
        elif name == "acted":
            self._acted(answer)
        elif name in ("imported", "forgotten", "recovered"):
            self.message = answer
            self.busy = False
            self.load()

    def _failed(self, name: str, why_: str) -> None:
        if name == "list":
            self.problem, self.busy = why_, False
            self.render()
        elif name == "acted":
            key, action = self.acting or ("", "")
            self.acting, self.busy = None, False
            self.message = why_
            if action != "appeal":
                self.status[key] = {"error": why_}
            self.render()
        else:                                                   # import, forget, recover: said, the list as it was
            self.busy = False
            self._enable()
            self._say(why_)

    # ---------------------------------------------------------------- drawing
    def render(self) -> None:
        self.fold.button.setText(f"My uploads · {len(self.rows)} saved credentials")
        self._enable()
        _clear(self.list_box)
        self.table_box, self.counted = None, None
        if self.problem is not None:
            self.said.setText(self.problem)
            return
        self.said.setText(self.message)
        if self.rows:
            self.list_box.addWidget(self._filters())
        holder = QWidget()
        holder.setObjectName("plain")
        self.table_box = QVBoxLayout(holder)
        self.table_box.setContentsMargins(0, 0, 0, 0)
        self.table_box.setSpacing(6)
        self.list_box.addWidget(holder)
        self._table()

    def _enable(self) -> None:
        for widget in (*self.tools, self.recover_save):
            widget.setEnabled(not self.busy)

    def _filters(self) -> QWidget:
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        search = QLineEdit(self.f["q"])
        search.setPlaceholderText("Search your uploads")
        search.setAccessibleName("Title or upload ID")
        search.setClearButtonEnabled(True)
        search.textChanged.connect(lambda text: self._filter("q", text))
        fields = [("Title or upload ID", search)]
        servers = cb.owned_servers(self.rows)
        if len(servers) > 1:
            server = QComboBox()
            server.setAccessibleName("Original server")
            server.addItem("any", "")
            for value in servers:
                server.addItem(value, value)
            server.setCurrentIndex(max(0, server.findData(self.f["server"])))
            server.activated.connect(lambda _i: self._filter("server", server.currentData() or ""))
            fields.append(("Original server", server))
        seen = QComboBox()
        seen.setAccessibleName("Visibility")
        for value, words in cb.OWNED_VISIBILITY:
            seen.addItem(words, value)
        seen.setCurrentIndex(max(0, seen.findData(self.f["visibility"])))
        seen.activated.connect(lambda _i: self._filter("visibility", seen.currentData() or ""))
        fields.append(("Visibility", seen))
        for words, widget in fields:
            box = QWidget()
            box.setObjectName("plain")
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(_label(words, "small", wrap=False))
            column.addWidget(widget)
            line.addWidget(box, 0, Qt.AlignBottom)
        line.addWidget(_button("Clear", self.clear_filters), 0, Qt.AlignBottom)
        self.counted = _label("", "small", wrap=False)
        line.addWidget(self.counted, 0, Qt.AlignBottom)
        line.addStretch(1)
        return row

    def _filter(self, key: str, value: str) -> None:
        self.f[key] = value
        self.page = 0
        self._table()

    def clear_filters(self) -> None:
        self.f = {"q": "", "server": "", "visibility": ""}
        self.page = 0
        self.render()

    def _view(self) -> list[tuple[int, dict]]:
        return [(i, r) for i, r in enumerate(self.rows) if cb.owned_matches(r, self.f, self.status.get(cb.owner_key(r)))]

    def _table(self) -> None:
        """The uploads the filters let through, a page of them, with their state and controls."""
        if self.table_box is None:
            return
        _clear(self.table_box)
        view = self._view()
        self.page = cb.owned_page(len(view), self.page)
        if self.counted is not None:
            self.counted.setText(f"{len(view)} of {len(self.rows)} uploads match." if len(view) != len(self.rows) else "")
        shown = view[self.page * cb.OWNED_PAGE:(self.page + 1) * cb.OWNED_PAGE]
        cells = [[f"{js_text(r.get('title'))} · {js_text(r.get('id'))}\n{js_text(r.get('server'))}",
                  self._state(index, r), self._controls(index, r)] for index, r in shown]
        self.table_box.addWidget(GridTable(cb.OWNED_COLUMNS, cells, {0: 2, 1: 2, 2: 3}, left=True))
        if not cells:
            self.table_box.addWidget(_label(cb.NO_OWNED_MATCH if self.rows else cb.NO_OWNED, "tcell"))
        pages = cb.owned_pages(len(view))
        self.table_box.addWidget(_row(
            _button("Previous", lambda: self._turn(-1), enabled=self.page > 0 and not self.busy),
            _label(f"{self.page + 1} / {pages}", wrap=False),
            _button("Next", lambda: self._turn(1), enabled=(self.page + 1) * cb.OWNED_PAGE < len(view) and not self.busy)))

    def _turn(self, step: int) -> None:
        self.page += step
        self._table()

    def _state(self, index: int, row: dict) -> QWidget:
        """An upload's visibility or why it could not be read, its shared link, and a hold with its appeal."""
        status = self.status.get(cb.owner_key(row))
        cell, column = _cell(3)
        column.addWidget(_label(cb.owned_state(status)))
        link = cb.shared_link(status, js_text(row.get("server")))
        if link:
            shared = _rich(f"<a href='{cb.html_text(link)}' style='color: {theme.COLORS['accent']};'>Open shared link</a>")
            shared.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
            shared.linkActivated.connect(self.open_link)
            column.addWidget(shared)
        hold = cb.held(status)
        for line in hold["lines"]:
            column.addWidget(_label(line))
        if hold["appeal"]:
            column.addWidget(_Appeal("Appeal this hold", lambda text, index=index: self.appeal(index, text),
                                     enabled=not self.busy))
        _close(column)
        return cell

    def _controls(self, index: int, row: dict) -> QWidget:
        allowed = cb.owned_controls(self.status.get(cb.owner_key(row)))
        busy = self.busy
        seen = QComboBox()
        seen.setAccessibleName("Upload visibility")
        for value in cb.OWNED_CHOICES:                          # each shown in the language chosen, sent as it is
            seen.addItem(value, value)
        seen.setCurrentIndex(max(0, seen.findData(allowed["visibility"])))
        seen.setEnabled(allowed["editable"] and not busy)
        cell, column = _cell()
        cell.setProperty("fill", False)                     # the controls as wide as they need
        tools = QWidget()
        tools.setObjectName("plain")
        column.addWidget(tools)
        _close(column)
        grid = QGridLayout(tools)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        widgets = [
            _button("Refresh", lambda: self.act(index, "refresh", seen), enabled=not busy), seen,
            _button("Save visibility", lambda: self.act(index, "visibility", seen), enabled=allowed["editable"] and not busy),
            _button("Rotate private link", lambda: self.act(index, "rotate", seen), enabled=allowed["rotate"] and not busy),
            *([_button("Review", lambda: self.act(index, "open", seen), enabled=not busy)] if self.open_log else []),
            _button("Delete upload", lambda: self.act(index, "delete", seen), enabled=not busy),
            _button("Forget credential", lambda: self.forget(index), enabled=not busy)]
        for place, widget in enumerate(widgets):
            grid.addWidget(widget, place // 3, place % 3)
        grid.setColumnStretch(3, 1)
        return cell

    # ---------------------------------------------------------------- actions
    def act(self, index: int, action: str, seen: QComboBox) -> None:
        """An upload refreshed, its visibility saved, its private link replaced, its log reviewed, or the upload
        deleted."""
        row = self.rows[index]
        visibility = "private" if action == "rotate" else seen.currentData()
        if action == "delete" and not self.confirm(cb.ASK_DELETE):
            return
        if action == "rotate" and not self.confirm(cb.ASK_ROTATE):
            return
        if action == "visibility" and visibility == "public" and not self.confirm(cb.ASK_PUBLIC):
            return
        self._start(row, action, cb.owner_request(row, action, visibility))

    def appeal(self, index: int, statement: str) -> None:
        """A moderation hold appealed, then the upload read again."""
        if len(statement) < 10:
            self._say(cb.SHORT_APPEAL)
            return
        self._start(self.rows[index], "appeal", cb.owner_request(self.rows[index], "appeal", statement))

    def _start(self, row: dict, action: str, body: dict) -> None:
        self.acting = (cb.owner_key(row), action)
        self.busy = True
        self.render()

        def work():
            result = self._post(body)
            if action == "delete":
                self._post({"action": "forget", "owner": row})
                return {"deleted": True}
            if action == "appeal":
                return {"status": self._post(cb.owner_request(row, "refresh"))}
            if action == "open":
                if isinstance(result, dict) and _truthy(result.get("error")):   # ``api()``: an answer with an error failed
                    raise ValueError(js_text(result["error"]))
                return {"log": result}
            return {"status": result}
        self._run("acted", work)

    def _acted(self, answer) -> None:
        key, action = self.acting or ("", "")
        self.acting, self.busy = None, False
        if action == "open":                                    # its log reviewed; the upload's state and the words kept
            self.render()
            if self.open_log is not None:
                self.open_log(_dict(answer).get("log"))
            return
        if action == "delete":
            self.status.pop(key, None)
            self.message = cb.owned_done("delete")
            self.load()
            return
        self.status[key] = _dict(answer).get("status")
        self.message = cb.APPEAL_SENT if action == "appeal" else cb.owned_done(action)
        self.render()

    def forget(self, index: int) -> None:
        """A credential forgotten here; the upload stays on its server."""
        if not self.confirm(cb.ASK_FORGET):
            return
        row = self.rows[index]
        self.busy = True
        self._enable()
        self._run("forgotten", lambda: (self._post({"action": "forget", "owner": row}),
                                        "Local credential forgotten; server log unchanged.")[1])

    def recover(self) -> None:
        """An older upload's credential saved from its server, ID and delete token."""
        try:
            row = cb.clean_owner({"server": self.recover_server.text().strip(), "id": self.recover_id.text().strip(),
                                  "delete_token": self.recover_token.text().strip()})
        except ValueError as problem:
            self._say(str(problem))
            return
        self.busy = True
        self._enable()
        self._run("recovered", lambda: (self._post({"action": "import", "owners": [row]}),
                                        "Credential saved locally. Refresh to verify it with the original server.")[1])

    def import_backup(self) -> None:
        path = self.choose_file()
        if not path:
            return
        try:
            if os.path.getsize(path) > cb.OWNED_BACKUP_LIMIT:
                raise ValueError("Backup exceeds 2 MiB")
            with open(path, encoding="utf-8", errors="replace") as handle:
                owners = cb.read_backup(json.loads(handle.read()))
        except (OSError, ValueError) as problem:
            self._say(str(problem))
            return
        if not self.confirm(cb.ASK_IMPORT):
            return
        self.busy = True
        self._enable()
        self._run("imported", lambda: (self._post({"action": "import", "owners": owners}),
                                       "Credentials imported. Refresh an upload to verify access.")[1])

    def export_backup(self) -> None:
        """The credentials saved to a private backup (``PRIVATE-combat-log-credentials.json``)."""
        path = self.save_file(cb.OWNED_FILE)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(cb.owned_backup(self.rows), indent=2, ensure_ascii=False))
        except OSError as problem:
            self._say(str(problem))

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, "Import private backup", "", "Backups (*.json)")
        return path

    def _ask_save(self, name: str) -> str:
        path, _kind = QFileDialog.getSaveFileName(self, "Export private credentials", name, "JSON (*.json)")
        return path


class Identities(QFrame):
    """My Character Identities (identity.js). ``call`` sends a request to the share server (``identity_call``);
    ``confirm`` stands in for the question."""

    def __init__(self, api: AppApi | None, call=None, confirm=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("note")
        self.api = api
        self.call = call or identity_call
        self.confirm = confirm or (lambda words: _ask(self, words))
        self.tasks = Tasks(self) if api is not None else None
        if self.tasks is not None:
            self.tasks.done.connect(self._done)
            self.tasks.failed.connect(self._failed)
        self.base, self.minimum, self.message, self.busy = "", cb.CLAIM_MINIMUM, "", False
        self.rows: list[dict] = []
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(6)
        self.load()

    def stop(self) -> None:
        if self.tasks is not None:
            self.tasks.stop()

    def _get(self, path: str):
        return self.api.get(path, timeout=TIMEOUT)

    # ---------------------------------------------------------------- reading
    def load(self) -> None:
        """The share server, the characters your recordings can claim, and the claims kept here with their state."""
        if self.tasks is None:
            return

        def work():
            base = cb._server_of(_dict(self._get("/api/logserver")).get("url"))
            if not base:
                return {"base": ""}
            proof = cb.evidence(self._get("/api/log-ownership"), base)
            mine = [c for c in _list(self._get("/api/identity-claims")) if isinstance(c, dict) and c.get("server") == base]
            characters, minimum = [], cb.CLAIM_MINIMUM
            if proof:
                out = _dict(self.call(base, "/api/v1/identity/claimable", "POST", {"evidence": proof}))
                characters, minimum = _list(out.get("characters")), out.get("min_recordings") or cb.CLAIM_MINIMUM
            statuses = {}
            for c in mine:
                key = cb.claim_key(c.get("name"), c.get("server_name"))
                try:
                    statuses[key] = self.call(base, "/api/v1/identity", token=c.get("token"))
                except Exception as exc:          # noqa: BLE001 - a claim the server refuses says why
                    statuses[key] = {"error": why(exc)}
            return {"base": base, "characters": characters, "mine": mine, "statuses": statuses, "minimum": minimum}
        self.tasks.run("load", work)

    def _done(self, name: str, answer) -> None:
        if name == "load":
            self.busy = False
            self._show(_dict(answer))
        elif name == "acted":
            self.message = js_text(answer)
            self.load()

    def _failed(self, name: str, why_: str) -> None:
        self.busy = False
        if name == "load":
            self._problem(why_)
        else:
            self.message = why_
            self.load()

    # ---------------------------------------------------------------- drawing
    def _problem(self, words: str) -> None:
        _clear(self.box)
        fold = Section("Your characters", None, True)
        fold.body_layout.addWidget(_label(words))
        fold.body_layout.addWidget(_row(_button("Retry", self.load)))
        self.box.addWidget(fold)

    def _show(self, answer: dict) -> None:
        _clear(self.box)
        self.base = answer.get("base") or ""
        if not self.base:
            fold = Section("Your characters", None, False)
            fold.body_layout.addWidget(_label(cb.NO_SHARE_SERVER, "small"))
            self.box.addWidget(fold)
            return
        self.minimum = answer.get("minimum") or cb.CLAIM_MINIMUM
        self.rows = cb.character_rows(answer.get("characters"), answer.get("mine"), answer.get("statuses") or {})
        fold = Section(f"Your characters · {len(self.rows)}", None, True)
        fold.body_layout.addWidget(_label(cb.identity_note(self.minimum, self.base), "small"))
        cells = [self._cells(index, row) for index, row in enumerate(self.rows)]
        fold.body_layout.addWidget(GridTable(cb.CHARACTER_COLUMNS, cells, {0: 1, 2: 3, 3: 2}, left=True))
        if not cells:
            fold.body_layout.addWidget(_label(cb.NO_CHARACTERS, "tcell"))
        said = _label(self.message, "small")
        said.setAccessibleName("Your characters status")
        self.said = said
        fold.body_layout.addWidget(_row(_button("Refresh", self.load, enabled=not self.busy), said))
        self.box.addWidget(fold)
        self.message = ""                                     # said once

    def _cells(self, index: int, row: dict) -> list:
        view = cb.character_view(row, self.minimum)
        name = cb.html_text(view["name"]) + (f" <span style='color: {theme.COLORS['muted']};'>· {cb.html_text(view['world'])}</span>"
                                             if view["world"] else "")
        state, column = _cell()
        column.addWidget(_rich(view["state"]))
        for note in view["notes"]:
            column.addWidget(_note_box(note))
        _close(column)
        actions, stack = _cell()
        if "opt_out" in view:
            stack.addWidget(WrapCheck(cb.OPT_OUT, view["opt_out"], not self.busy,
                                      lambda checked: self.opt_out(index, checked)))
        if view.get("appeal"):
            stack.addWidget(_Appeal("Appeal the revocation", lambda text: self.appeal(index, text), enabled=not self.busy))
        buttons = []
        for action, words, enabled, tip in view["actions"]:
            button = _button(words, lambda action=action: self.act(index, action), enabled=enabled and not self.busy)
            if tip:
                button.setToolTip(tip)
            buttons.append(button)
        stack.addWidget(_row(*buttons))
        _close(stack)
        return [_rich(name), view["recordings"], state, actions]

    # ---------------------------------------------------------------- actions
    def _run(self, work) -> None:
        """An action, the list disabled meanwhile, then the list read again (``run``)."""
        if self.tasks is None:
            return
        self.busy = True
        for widget in self.findChildren(QPushButton) + self.findChildren(QCheckBox):
            widget.setEnabled(False)
        self.tasks.run("acted", work)

    def _claims(self) -> list:
        return _list(self._get("/api/identity-claims"))

    def _save(self, rows: list) -> None:
        self.api.post("/api/identity-claims", {"action": "replace", "claims": rows}, timeout=TIMEOUT)

    def act(self, index: int, action: str) -> None:
        row, base = self.rows[index], self.base
        stored = row.get("stored") or {}
        if action == "claim":
            def work():
                proof = cb.evidence(self._get("/api/log-ownership"), base)
                out = _dict(self.call(base, "/api/v1/identity/claim", "POST",
                                      {"name": row.get("name"), "server": row.get("server_name") or "", "evidence": proof},
                                      token=stored.get("token")))
                if _truthy(out.get("token")):
                    self._save(cb.kept_claims(self._claims(), {
                        "server": base, "name": row.get("name"), "server_name": row.get("server_name") or "",
                        "token": out["token"], "status": out.get("status"), "claimed_at": out.get("claimed_at")}))
                elif stored:
                    self._save(cb.kept_claims(self._claims(), {**stored, "status": out.get("status")}))
                return cb.claim_done(out.get("status"))
        elif action == "release":
            if not self.confirm(cb.ASK_RELEASE):
                return

            def work():
                self.call(base, "/api/v1/identity/release", "POST", {}, token=stored.get("token"))
                self._save(cb.without_claim(self._claims(), stored))
                return "Released."
        else:                                                 # forget
            def work():
                self._save(cb.without_claim(self._claims(), stored))
                return "Local credential forgotten."
        self._run(work)

    def opt_out(self, index: int, hidden: bool) -> None:
        """Hidden in other uploaders' public logs, leaderboards and parse brackets, or shown by name again."""
        token, base = (self.rows[index].get("stored") or {}).get("token"), self.base

        def work():
            self.call(base, "/api/v1/identity/preferences", "POST", {"opt_out": bool(hidden)}, token=token)
            return cb.opt_out_done(bool(hidden))
        self._run(work)

    def appeal(self, index: int, statement: str) -> None:
        if len(statement) < 10:
            self.said.setText(cb.SHORT_APPEAL)
            return
        token, base = (self.rows[index].get("stored") or {}).get("token"), self.base

        def work():
            self.call(base, "/api/v1/identity/appeal", "POST", {"statement": statement}, token=token)
            return cb.APPEAL_SENT
        self._run(work)
