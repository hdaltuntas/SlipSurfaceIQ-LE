"""Text catalogue with templates (no Qt): used by the UI language switch and
the PDF / text reports.

An entry maps a Turkish source string to its translation. Keys may contain
positional ``{}`` fields; such an entry is a template matching a whole dynamic
string, and the captured values are translated recursively and inserted in
order. Multi-line text is translated line by line.
"""

from __future__ import annotations

import re


class Catalog:
    PREFIXES = ("⚠ ", "▾  ", "• ")

    def __init__(self, entries: dict[str, str]) -> None:
        self.exact = dict(entries)
        patterns = []
        for key, value in entries.items():
            if "{}" in key:
                parts = [re.escape(p) for p in key.split("{}")]
                # numbered labels ("Destek {}", "Kaplama {}") only take a number,
                # so they never swallow longer captions that share the first word
                numbered = key.endswith(" {}") and key.count("{}") == 1 and ":" not in key
                group = r"(\d+)" if numbered else "(.*?)"
                patterns.append((re.compile(group.join(parts), re.S), value))
        patterns.sort(key=lambda kv: -len(kv[0].pattern))  # most specific first
        self.patterns = patterns
        # templates spanning lines are tried on the whole text before the
        # line-by-line fallback
        self.multiline = [
            (rx, v) for rx, v in patterns if "\n" in rx.pattern or "\\n" in rx.pattern
        ]

    def translate(self, source: str) -> str:
        if not isinstance(source, str) or not source:
            return source
        hit = self.exact.get(source)
        if hit is not None:
            return hit
        for prefix in self.PREFIXES:
            if source.startswith(prefix):
                return prefix + self.translate(source[len(prefix) :])
        stripped = source.strip()
        if stripped != source:
            if not stripped:
                return source
            lead = source[: len(source) - len(source.lstrip())]
            trail = source[len(source.rstrip()) :]
            return lead + self.translate(stripped) + trail
        if "\n" in source:
            for rx, template in self.multiline:
                m = rx.fullmatch(source)
                if m:
                    return template.format(*(self.translate(g) for g in m.groups()))
            return "\n".join(self.translate(line) for line in source.split("\n"))
        for rx, template in self.patterns:
            m = rx.fullmatch(source)
            if m:
                return template.format(*(self.translate(g) for g in m.groups()))
        return source
