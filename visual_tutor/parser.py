import re

from visual_schema import expand, parse_tag

_SENTENCE = re.compile(r"(.+?[.!?]\s+)(.*)", re.S)


class VisualStreamParser:
    def __init__(self, on_text, on_visual):
        self.on_text = on_text
        self.on_visual = on_visual
        self._buf = ""

    async def feed(self, token: str) -> None:
        self._buf += token
        while True:
            start = self._buf.find("[[")
            if start == -1:
                await self._flush_sentences()
                return
            end = self._buf.find("]]", start + 2)
            if end == -1:
                prefix = self._buf[:start]
                self._buf = self._buf[start:]
                if prefix.strip():
                    await self.on_text(prefix)
                return
            prefix = self._buf[:start]
            if prefix.strip():
                await self.on_text(prefix)
            tag = parse_tag(self._buf[start:end + 2])
            if tag:
                await self.on_visual(expand(tag["action"], tag["object"], tag["attributes"]))
            self._buf = self._buf[end + 2:]

    async def close(self) -> None:
        if self._buf.strip():
            await self.on_text(self._buf)
        self._buf = ""

    async def _flush_sentences(self) -> None:
        while True:
            match = _SENTENCE.match(self._buf)
            if not match:
                return
            sentence, rest = match.group(1), match.group(2)
            if sentence.strip():
                await self.on_text(sentence)
            self._buf = rest
