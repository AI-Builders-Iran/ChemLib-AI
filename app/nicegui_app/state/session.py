"""Per-user / per-tab state.

NiceGUI has three relevant storage scopes, and picking the wrong one was the
cause of a real bug ("admin login doesn't stick"):

* ``app.storage.client`` — tied to one specific *connection*. Per its own
  docstring, it "is already discarded when the connection to the client is
  lost through a page reload **or a navigation**." Since every ``@ui.page``
  route here is a separate page (``ui.navigate.to("/")`` after login is a
  real navigation, not an SPA transition), anything stored here during
  ``/login`` was gone the instant the browser landed on ``/``. This is why
  logging in correctly still never showed the admin-only upload controls.
* ``app.storage.user`` — stored server-side, keyed by a signed session
  cookie, shared across every tab/page of the same browser. Survives
  navigation. This is what "am I the logged-in admin" needs, and is used for
  :func:`is_admin`/:func:`set_admin` below.
* ``app.storage.tab`` — also survives navigation, but stays private to one
  browser tab (a second tab gets its own). Used for chat history and the
  selected scope, so a conversation isn't lost just by visiting Documents
  and coming back — the original ``app.storage.client`` bug applied to these
  too, just less visibly than the login issue.

The private ``SessionVectorStore`` instance itself is not JSON-serializable
and can't live in any ``app.storage.*`` dict, so it stays in a small
server-side registry keyed by client id, cleaned up on disconnect.

OCR-mode preference is intentionally left on ``app.storage.client``: reading
it currently happens before a tab's connection is established on some pages
(``app.storage.tab`` requires an active socket connection), and it's a minor
preference, not core functionality — documented as a known limitation.
"""

from __future__ import annotations

from nicegui import app, ui

from ..services import backend

_private_stores: dict[str, object] = {}

ADMIN_KEY = "dx_is_admin"
CHAT_LIBRARY_KEY = "dx_chat_library"
CHAT_PRIVATE_KEY = "dx_chat_private"
SCOPE_LIBRARY_KEY = "dx_scope_library"
SCOPE_PRIVATE_KEY = "dx_scope_private"
MODE_KEY = "dx_chat_mode"  # "library" | "private"


def client_id() -> str:
    return ui.context.client.id


def is_admin() -> bool:
    return bool(app.storage.user.get(ADMIN_KEY, False))


def set_admin(value: bool) -> None:
    app.storage.user[ADMIN_KEY] = value


def private_store():
    """This tab's in-memory store; created on first use, never persisted."""
    cid = client_id()
    if cid not in _private_stores:
        _private_stores[cid] = backend.new_session_store()
        ui.context.client.on_disconnect(lambda: _private_stores.pop(cid, None))
    return _private_stores[cid]


def has_private_store() -> bool:
    return client_id() in _private_stores


def clear_private_store() -> None:
    store = _private_stores.pop(client_id(), None)
    if store is not None:
        store.clear()


def chat_messages(mode: str) -> list[dict]:
    """``mode`` is "library" or "private" — each has its own conversation."""
    key = CHAT_LIBRARY_KEY if mode == "library" else CHAT_PRIVATE_KEY
    return app.storage.tab.setdefault(key, [])


def clear_chat(mode: str) -> None:
    key = CHAT_LIBRARY_KEY if mode == "library" else CHAT_PRIVATE_KEY
    app.storage.tab[key] = []


OCR_MODE_KEY = "dx_ocr_mode"


def ocr_mode() -> str:
    if OCR_MODE_KEY not in app.storage.client:
        app.storage.client[OCR_MODE_KEY] = backend.default_ocr_mode()
    return app.storage.client[OCR_MODE_KEY]


def set_ocr_mode(value: str) -> None:
    app.storage.client[OCR_MODE_KEY] = value


def scope(mode: str) -> str | None:
    key = SCOPE_LIBRARY_KEY if mode == "library" else SCOPE_PRIVATE_KEY
    return app.storage.tab.get(key)


def set_scope(mode: str, document_id: str | None) -> None:
    key = SCOPE_LIBRARY_KEY if mode == "library" else SCOPE_PRIVATE_KEY
    app.storage.tab[key] = document_id


SUMMARY_DOC_KEY = "dx_summary_doc_"  # + mode; kept apart from the chat scope so picking a summary never narrows the chat


def summary_doc(mode: str) -> str | None:
    """Document last chosen on the summary page (or via the summary button on Documents)."""
    return app.storage.tab.get(SUMMARY_DOC_KEY + mode)


def set_summary_doc(mode: str, document_id: str | None) -> None:
    app.storage.tab[SUMMARY_DOC_KEY + mode] = document_id
