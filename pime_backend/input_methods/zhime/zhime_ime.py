"""PIME text service for zhime: maps Windows key events onto zhime.engine.Session.

Keys while composing:
  Zhuyin keys / letters / space   -> into the buffer (space is tone 1)
  Shift+letter                    -> uppercase letter (English)
  Enter                           -> commit the highlighted candidate
  Down / Tab, Up / Shift+Tab      -> move the highlight along the candidate bar
  Ctrl+1..9                       -> commit that candidate directly
  Backspace / Esc                 -> delete last key / cancel
  Shift+punctuation               -> commit, then full-width punctuation
"""

from keycodes import *  # noqa: F403 (VK_* constants)
from textService import TextService

from zhime.engine import Engine, Session

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


# Keys that type Zhuyin symbols or tones on the Daqian layout (space handled separately).
ZHUYIN_KEYS = set("1qaz2wsxedcrfv5tgbyhnujm8ik,9ol.0p;/-6347")
FULLWIDTH = {
    ",": "，", ".": "。", "/": "？", ";": "：", "'": "、", "1": "！",
    "[": "「", "]": "」", "9": "（", "0": "）", "\\": "、",
}
SHIFTED = {"<": ",", ">": ".", "?": "/", ":": ";", '"': "'", "!": "1",
           "{": "[", "}": "]", "(": "9", ")": "0", "|": "\\"}


class ZhimeTextService(TextService):
    def __init__(self, client):
        TextService.__init__(self, client)
        self.session = Session(engine())

    def onActivate(self):
        TextService.onActivate(self)
        self.customizeUI(candFontSize=16, candPerRow=9, candUseCursor=True)
        self.setSelKeys("123456789")

    def onDeactivate(self):
        self.session.clear()
        self._render()
        TextService.onDeactivate(self)

    def onCompositionTerminated(self, forced):
        TextService.onCompositionTerminated(self, forced)
        self.session.clear()

    # ---- which keys we take -------------------------------------------------

    def filterKeyDown(self, keyEvent):
        if keyEvent.isKeyDown(VK_CONTROL) or keyEvent.isKeyDown(VK_MENU):
            return self.session.composing and ord("1") <= keyEvent.keyCode <= ord("9")
        if self.session.composing:
            return True
        ch = chr(keyEvent.charCode) if keyEvent.isChar() else ""
        if ch in SHIFTED:
            return True
        return ch.lower() in ZHUYIN_KEYS or ch.isalpha()

    def onKeyDown(self, keyEvent):
        s = self.session
        code = keyEvent.keyCode
        ch = chr(keyEvent.charCode) if keyEvent.isChar() else ""

        if keyEvent.isKeyDown(VK_CONTROL):
            if ord("1") <= code <= ord("9"):
                self._commit(s.commit(code - ord("1")))
            return True
        if code == VK_RETURN:
            self._commit(s.commit())
        elif code == VK_ESCAPE:
            s.clear()
        elif code == VK_BACK:
            s.backspace()
        elif code in (VK_DOWN, VK_RIGHT) or (code == VK_TAB and not keyEvent.isKeyDown(VK_SHIFT)):
            s.move(+1)
        elif code in (VK_UP, VK_LEFT) or code == VK_TAB:
            s.move(-1)
        elif ch in SHIFTED:
            text = s.commit() if s.composing else ""
            self._commit(text + FULLWIDTH.get(SHIFTED[ch], ch))
        elif ch == " " or ch.lower() in ZHUYIN_KEYS or ch.isalpha():
            s.type(ch)
        elif ch:
            # anything else (e.g. '=') ends the composition and is typed as-is
            self._commit((s.commit() if s.composing else "") + ch)
        self._render()
        return True

    # ---- output -------------------------------------------------------------

    def _commit(self, text):
        if text:
            self.setCommitString(text)

    def _render(self):
        s = self.session
        self.setCompositionString(s.preview if s.composing else "")
        self.setCompositionCursor(len(s.preview) if s.composing else 0)
        if s.composing and s.cands:
            self.setCandidateList([c.text for c in s.cands])
            self.setCandidateCursor(s.sel)
            self.setShowCandidates(True)
        else:
            self.setCandidateList([])
            self.setShowCandidates(False)
