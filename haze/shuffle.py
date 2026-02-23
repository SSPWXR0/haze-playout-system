from __future__ import annotations

import random


class ShuffleDeck:
    def __init__(self, n: int, carry_over: int = 3):
        self._n = n
        self._carry_over = min(carry_over, n // 2)
        self._deck: list[int] = []
        self._pos: int = 0
        self._last_tail: list[int] = []
        self._build()

    def _build(self):
        deck = list(range(self._n))
        random.shuffle(deck)

        if self._last_tail:
            for i, idx in enumerate(deck):
                if idx not in self._last_tail:
                    deck[0], deck[i] = deck[i], deck[0]
                    break

        self._last_tail = deck[-self._carry_over:] if self._carry_over else []
        self._deck = deck
        self._pos = 0

    def current(self) -> int:
        return self._deck[self._pos]

    def advance(self):
        self._pos += 1
        if self._pos >= self._n:
            self._build()

    def rewind(self):
        self._pos = max(0, self._pos - 1)

    def reset(self, n: int | None = None):
        if n is not None:
            self._n = n
            self._carry_over = min(self._carry_over, n // 2)
            self._last_tail = []
        self._build()