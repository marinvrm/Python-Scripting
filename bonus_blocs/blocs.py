#!/usr/bin/env python3
"""BLOCS : un jeu de blocs qui tombent (facon Tetris), en Python pur.

Un seul fichier, zero dependance : uniquement la bibliotheque standard.
Tout ce qui s'affiche et tout ce qui s'entend est fabrique par le code :
  - les images (blocs en relief, halos, particules, fond etoile) sont des
    PNG ecrits octet par octet avec zlib et struct ;
  - les sons sont synthetises echantillon par echantillon, ecrits en WAV
    avec le module wave et joues par winsound (Windows uniquement).

Le fichier est coupe en deux :
  - la classe Game contient toutes les regles, sans rien afficher. Elle se
    teste sans fenetre (voir test_blocs.py) et publie des "evenements"
    (piece posee, lignes effacees, niveau...) ;
  - la classe App lit le clavier, transforme ces evenements en animations
    et dessine le tout dans un canevas tkinter.

Commandes :
    fleches gauche / droite   deplacer
    fleche bas                descendre plus vite
    fleche haut, X            tourner (sens horaire)
    W, Z, Ctrl                tourner (sens anti-horaire)
    ESPACE                    lacher la piece
    C, Maj                    mettre en reserve
    P, ECHAP                  pause
    R                         recommencer
    M                         couper le son
    F                         afficher les images par seconde

Usage :
    python blocs.py              # jouer
    python blocs.py --niveau 5   # choisir le niveau de depart
"""

from __future__ import annotations

import argparse
import base64
from array import array
import json
import math
import random
import struct
import tempfile
import threading
import time
import wave
import zlib
from pathlib import Path

# --------------------------------------------------------------------------
# Regles
# --------------------------------------------------------------------------

WIDTH = 10
HEIGHT = 22  # dont 2 lignes cachees au-dessus du plateau visible
HIDDEN = 2

LOCK_DELAY = 0.5  # temps au sol avant que la piece se fige
MAX_RESETS = 15  # nombre de mouvements au sol qui relancent ce delai
SOFT_DROP_INTERVAL = 0.035
LINE_POINTS = (0, 100, 300, 500, 800)
TSPIN_POINTS = (400, 800, 1200, 1600, 1600)
PERFECT_POINTS = (0, 800, 1200, 1800, 2000)

# Forme de depart de chaque piece dans sa boite n x n (y vers le bas).
SHAPES = {
    "I": (4, ((0, 1), (1, 1), (2, 1), (3, 1))),
    "O": (2, ((0, 0), (1, 0), (0, 1), (1, 1))),
    "T": (3, ((1, 0), (0, 1), (1, 1), (2, 1))),
    "S": (3, ((1, 0), (2, 0), (0, 1), (1, 1))),
    "Z": (3, ((0, 0), (1, 0), (1, 1), (2, 1))),
    "J": (3, ((0, 0), (0, 1), (1, 1), (2, 1))),
    "L": (3, ((2, 0), (0, 1), (1, 1), (2, 1))),
}


def _rotate_cw(cells, size):
    """Quart de tour horaire dans une boite size x size."""
    return tuple((size - 1 - y, x) for x, y in cells)


# La case i d'une rotation est l'image de la case i de la precedente :
# l'affichage s'en sert pour faire glisser chaque case vers sa place.
ROTATIONS = {}
for _kind, (_size, _cells) in SHAPES.items():
    _states = [tuple(_cells)]
    for _ in range(3):
        _states.append(_rotate_cw(_states[-1], _size))
    ROTATIONS[_kind] = _states


def _flip_y(table):
    """Les tables officielles ont y vers le haut, le plateau y vers le bas."""
    return {k: tuple((x, -y) for x, y in v) for k, v in table.items()}


# Decalages essayes quand une rotation est bloquee ("wall kicks", norme SRS).
# Sans eux, une piece collee a un mur ne pourrait pas tourner.
KICKS = _flip_y({
    (0, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (1, 0): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (1, 2): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (2, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (2, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (3, 2): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (3, 0): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (0, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
})
KICKS_I = _flip_y({
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)),
})


def gravity_interval(level: int) -> float:
    """Secondes pour descendre d'une ligne (courbe de la norme officielle)."""
    level = max(1, min(level, 20))
    return (0.8 - (level - 1) * 0.007) ** (level - 1)


class Game:
    """Etat complet d'une partie, independant de tout affichage.

    Chaque changement notable est ajoute a self.events sous forme de
    dictionnaire ; l'affichage les consomme pour lancer ses animations.
    """

    def __init__(self, seed=None, level: int = 1):
        self.rng = random.Random(seed)
        self.board = [[None] * WIDTH for _ in range(HEIGHT)]
        self.bag = []
        self.queue = []
        self.events = []
        self.start_level = level
        self.level = level
        self.score = 0
        self.lines = 0
        self.pieces = 0
        self.combo = -1
        self.b2b_ready = False  # dernier effacement "difficile" (Tetris, T-spin)
        self.last_rotate = False  # derniere action reussie = rotation
        self.hold_kind = None
        self.hold_used = False
        self.over = False
        self._fill_queue()
        self.spawn()

    # --- pieces ---------------------------------------------------------

    def _next_kind(self) -> str:
        """Tirage par sacs de 7 : chaque piece sort une fois par sac."""
        if not self.bag:
            self.bag = list(SHAPES)
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _fill_queue(self):
        while len(self.queue) < 5:
            self.queue.append(self._next_kind())

    def spawn(self, kind=None):
        from_queue = kind is None
        if from_queue:
            kind = self.queue.pop(0)
            self._fill_queue()
        self.kind = kind
        self.rot = 0
        self.x = 4 if kind == "O" else 3
        self.y = 1 if kind == "I" else 2  # entierement visible
        self.gravity_timer = 0.0
        self.lock_timer = 0.0
        self.resets = 0
        self.lowest = self.y
        self.last_rotate = False
        self.events.append({"type": "spawn", "from_queue": from_queue})
        if self.collides(self.x, self.y, self.rot):
            self._game_over()

    def _game_over(self):
        if not self.over:
            self.over = True
            self.events.append({"type": "over"})

    def cells(self, x=None, y=None, rot=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        rot = self.rot if rot is None else rot
        return [(x + cx, y + cy) for cx, cy in ROTATIONS[self.kind][rot]]

    def occupied(self, cx, cy) -> bool:
        """Case pleine ; les bords du plateau comptent comme pleins."""
        if not (0 <= cx < WIDTH and 0 <= cy < HEIGHT):
            return True
        return self.board[cy][cx] is not None

    def collides(self, x, y, rot) -> bool:
        return any(self.occupied(cx, cy) for cx, cy in self.cells(x, y, rot))

    def grounded(self) -> bool:
        return self.collides(self.x, self.y + 1, self.rot)

    def ghost_y(self) -> int:
        y = self.y
        while not self.collides(self.x, y + 1, self.rot):
            y += 1
        return y

    def _t_corners(self) -> int:
        """Regle des 3 coins : un T tourne dans un trou entoure = T-spin."""
        cx, cy = self.x + 1, self.y + 1
        return sum(self.occupied(cx + dx, cy + dy)
                   for dx in (-1, 1) for dy in (-1, 1))

    # --- actions du joueur ----------------------------------------------

    def _moved(self):
        """Un mouvement au sol relance le delai de verrouillage (limite)."""
        if self.grounded() and self.resets < MAX_RESETS:
            self.lock_timer = 0.0
            self.resets += 1

    def move(self, dx: int) -> bool:
        if self.over or self.collides(self.x + dx, self.y, self.rot):
            return False
        self.x += dx
        self.last_rotate = False
        self._moved()
        return True

    def rotate(self, direction: int) -> bool:
        if self.over:
            return False
        if self.kind == "O":
            return True
        new = (self.rot + direction) % 4
        table = KICKS_I if self.kind == "I" else KICKS
        for dx, dy in table[(self.rot, new)]:
            if not self.collides(self.x + dx, self.y + dy, new):
                self.x += dx
                self.y += dy
                self.rot = new
                self.last_rotate = True
                self.events.append({"type": "rotate"})
                self._moved()
                return True
        return False

    def step_down(self) -> bool:
        if self.grounded():
            return False
        self.y += 1
        self.last_rotate = False
        if self.y > self.lowest:
            self.lowest = self.y
            self.resets = 0
            self.lock_timer = 0.0
        return True

    def hard_drop(self) -> int:
        if self.over:
            return 0
        start = self.cells()
        rows = 0
        while self.step_down():
            rows += 1
        self.score += 2 * rows
        self.events.append({"type": "harddrop", "kind": self.kind,
                            "from": start, "to": self.cells(), "rows": rows})
        self.lock()
        return rows

    def hold(self) -> bool:
        if self.over or self.hold_used:
            return False
        current = self.kind
        if self.hold_kind is None:
            self.spawn()
        else:
            self.spawn(self.hold_kind)
        self.hold_kind = current
        self.hold_used = True
        self.events.append({"type": "hold"})
        return True

    # --- temps qui passe ------------------------------------------------

    def tick(self, dt: float, soft: bool = False):
        if self.over:
            return
        interval = gravity_interval(self.level)
        if soft:
            interval = min(interval, SOFT_DROP_INTERVAL)
        self.gravity_timer += dt
        while self.gravity_timer >= interval:
            self.gravity_timer -= interval
            if self.step_down():
                if soft:
                    self.score += 1
            else:
                self.gravity_timer = 0.0
                break
        if self.grounded():
            self.lock_timer += dt
            if self.lock_timer >= LOCK_DELAY:
                self.lock()
        else:
            self.lock_timer = 0.0

    def lock(self):
        cells = self.cells()
        tspin = self.kind == "T" and self.last_rotate and self._t_corners() >= 3
        for cx, cy in cells:
            self.board[cy][cx] = self.kind
        self.pieces += 1
        self.events.append({"type": "lock", "cells": cells, "kind": self.kind})
        if all(cy < HIDDEN for _, cy in cells):
            self._game_over()  # piece figee entierement hors du plateau

        full = [r for r in range(HEIGHT) if all(self.board[r])]
        n = min(len(full), 4)  # une piece couvre 4 lignes au plus
        level = self.level
        points = (TSPIN_POINTS if tspin else LINE_POINTS)[n] * level
        difficult = n == 4 or (tspin and n > 0)
        b2b = difficult and self.b2b_ready
        if b2b:
            points = points * 3 // 2
        if n:
            self.b2b_ready = difficult
            self.combo += 1
            points += 50 * self.combo * level
        else:
            self.combo = -1

        before = shift = None
        if n:
            before = [row[:] for row in self.board]
            kept = [r for r in range(HEIGHT) if r not in full]
            # decalage vers le bas de chaque ligne du nouveau plateau
            shift = [n] * n + [sum(1 for f in full if f > r) for r in kept]
            self.board = ([[None] * WIDTH for _ in range(n)]
                          + [self.board[r] for r in kept])
        perfect = n > 0 and not any(any(row) for row in self.board)
        if perfect:
            points += PERFECT_POINTS[n] * level
        self.score += points

        if n or tspin:
            self.events.append({
                "type": "clear", "rows": full, "count": n, "tspin": tspin,
                "b2b": b2b, "combo": self.combo if n else 0,
                "perfect": perfect, "points": points,
                "before": before, "shift": shift,
            })
        if n:
            self.lines += n
            new_level = self.start_level + self.lines // 10
            if new_level != self.level:
                self.level = new_level
                self.events.append({"type": "level", "level": new_level})

        self.hold_used = False
        if not self.over:
            self.spawn()


# --------------------------------------------------------------------------
# Couleurs
# --------------------------------------------------------------------------


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


def mix(a, b, t):
    """Melange lineaire de deux couleurs RGB, t = 0 donne a, t = 1 donne b."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


BG_TOP = rgb("#070914")
BG_BOTTOM = rgb("#140a26")
BOARD_BG = rgb("#0b0e1c")
SLOT = rgb("#11152a")
PANEL = rgb("#0e1224")
PANEL_EDGE = rgb("#232a48")
TEXT = rgb("#eef0ff")
MUTED = rgb("#7a80a6")
GOLD = rgb("#ffd166")
WHITE = (255, 255, 255)
COLORS = {
    "I": rgb("#35d0f0"),
    "O": rgb("#ffd23f"),
    "T": rgb("#b36bff"),
    "S": rgb("#47e07b"),
    "Z": rgb("#ff4d6d"),
    "J": rgb("#4d7cff"),
    "L": rgb("#ff9a3c"),
}
GREY = rgb("#565c78")
# couleur du halo du plateau, qui change a chaque niveau
THEMES = [rgb(c) for c in ("#35d0f0", "#b36bff", "#ff4d6d", "#ffd23f",
                            "#47e07b", "#ff9a3c", "#4d7cff", "#ff5fd2")]


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    s = 1.7
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def ease_out_bounce(t):
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def clamp01(t):
    return 0.0 if t < 0 else (1.0 if t > 1 else t)


# --------------------------------------------------------------------------
# Images generees par le code
# --------------------------------------------------------------------------


def png_bytes(w, h, raw: bytes) -> bytes:
    """Encode des pixels RGBA (une ligne = octet de filtre + w*4 octets)."""
    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def rgba_bytes(w, h, pixel) -> bytes:
    """Calcule chaque pixel avec pixel(x, y) -> (r, g, b, a)."""
    out = bytearray()
    for y in range(h):
        out.append(0)
        for x in range(w):
            r, g, b, a = pixel(x, y)
            out += bytes((max(0, min(255, int(r))), max(0, min(255, int(g))),
                          max(0, min(255, int(b))), max(0, min(255, int(a)))))
    return bytes(out)


class Assets:
    """Toutes les images du jeu, calculees une fois au demarrage."""

    SHRINK_STEPS = 8
    FLASH_LEVELS = 6
    TRAIL_LEVELS = 8

    def __init__(self, tk, cell, mini, scale):
        self.tk = tk
        self.cell = cell
        self.mini_size = mini
        self.block = {k: self._block_levels(COLORS[k], cell) for k in COLORS}
        self.grey = self._block_levels(GREY, cell, levels=1)[0]
        self.ghost = {k: self._ghost(COLORS[k], cell) for k in COLORS}
        self.shrink = self._shrinking(cell)
        self.mini = {k: self._block_levels(COLORS[k], mini, levels=3, brightest=0.4)
                     for k in COLORS}
        self.mini_grey = self._block_levels(GREY, mini, levels=1)[0]
        self.mini_dim = {k: self._photo(mini, mini, rgba_bytes(
            mini, mini, self._block_pixel(mix(BG_TOP, COLORS[k], 0.16), mini, BG_TOP, 0)))
            for k in COLORS}
        self.trail = {k: self._trails(COLORS[k], cell) for k in COLORS}
        sizes = [max(2, round(s * scale)) for s in (3, 5, 7, 10, 14)]
        self.dot_sizes = sizes
        self.dots = {k: [self._dot(COLORS[k], s) for s in sizes] for k in COLORS}
        self.dots["W"] = [self._dot(WHITE, s) for s in sizes]
        self.dots["G"] = [self._dot(GOLD, s) for s in sizes]
        self.stars = [self._star(max(2, round(s * scale)), b)
                      for s in (2, 3, 5) for b in (0.35, 0.6, 1.0)]

    def _photo(self, w, h, raw):
        data = base64.b64encode(png_bytes(w, h, raw)).decode("ascii")
        return self.tk.PhotoImage(data=data, format="png")

    @staticmethod
    def _block_pixel(base, s, gap_color, flash):
        """Bloc en relief : degrade, biseau clair en haut, sombre en bas."""
        bevel = max(2, s // 9)
        hi = mix(base, WHITE, 0.45)
        lo = mix(base, (0, 0, 0), 0.45)
        side = mix(base, (0, 0, 0), 0.22)
        inner = s - 2

        def pixel(x, y):
            if x == 0 or y == 0 or x == s - 1 or y == s - 1:
                return (*gap_color, 255)
            u = (x - 1) / max(1, inner - 1)
            v = (y - 1) / max(1, inner - 1)
            dt, db = y - 1, s - 2 - y
            dl, dr = x - 1, s - 2 - x
            m = min(dt, db, dl, dr)
            if m < bevel:
                if m == dt:
                    c = hi
                elif m == db:
                    c = lo
                elif m == dl:
                    c = mix(base, WHITE, 0.18)
                else:
                    c = side
            else:
                c = mix(base, WHITE, 0.10 * (1 - v)) if v < 0.5 else \
                    mix(base, (0, 0, 0), 0.20 * (v - 0.5) * 2)
                # reflet brillant dans le coin superieur gauche
                d = math.hypot(u - 0.28, v - 0.26)
                if d < 0.24:
                    c = mix(c, WHITE, 0.32 * (1 - d / 0.24) ** 2)
            if flash:
                c = mix(c, WHITE, flash)
            return (*c, 255)
        return pixel

    def _block_levels(self, base, s, levels=None, brightest=0.85):
        """Niveau 0 = bloc normal, puis de plus en plus eclaire (flash)."""
        levels = levels or self.FLASH_LEVELS
        out = []
        for i in range(levels):
            flash = brightest * i / max(1, levels - 1)
            out.append(self._photo(s, s, rgba_bytes(
                s, s, self._block_pixel(base, s, BOARD_BG, flash))))
        return out

    def _ghost(self, base, s):
        border = max(2, s // 14)
        edge = mix(BOARD_BG, base, 0.75)
        fill = mix(BOARD_BG, base, 0.14)

        def pixel(x, y):
            if x == 0 or y == 0 or x == s - 1 or y == s - 1:
                return (*BOARD_BG, 255)
            m = min(x - 1, y - 1, s - 2 - x, s - 2 - y)
            return (*(edge if m < border else fill), 255)
        return self._photo(s, s, rgba_bytes(s, s, pixel))

    def _shrinking(self, s):
        """Bloc blanc qui retrecit : l'animation d'une ligne qui disparait."""
        out = []
        for i in range(self.SHRINK_STEPS):
            t = i / self.SHRINK_STEPS
            half = (s - 2) * (1 - t) / 2
            glow = mix(WHITE, GOLD, t)

            def pixel(x, y, half=half, glow=glow, t=t):
                dx = abs(x + 0.5 - s / 2)
                dy = abs(y + 0.5 - s / 2)
                if max(dx, dy) <= half:
                    return (*glow, 255)
                return (*mix(BOARD_BG, glow, 0.25 * (1 - t)), 255) \
                    if max(dx, dy) <= half + 2 else (*BOARD_BG, 255)
            out.append(self._photo(s, s, rgba_bytes(s, s, pixel)))
        return out

    def _trails(self, base, s):
        """Traine d'une piece lachee : bande verticale translucide."""
        out = []
        inset = max(2, s // 6)
        for i in range(1, self.TRAIL_LEVELS + 1):
            a = 150 * i / self.TRAIL_LEVELS
            c = mix(base, WHITE, 0.3)

            def pixel(x, _y, a=a, c=c):
                d = abs(x + 0.5 - s / 2) / (s / 2 - inset)
                if d >= 1:
                    return (0, 0, 0, 0)
                return (*c, a * (1 - d * d))
            row = rgba_bytes(s, 1, pixel)  # toutes les lignes sont identiques
            out.append(self._photo(s, s, row * s))
        return out

    def _dot(self, color, size):
        """Particule : point lumineux, blanc au centre, bord transparent."""
        r = size / 2

        def pixel(x, y):
            d = math.hypot(x + 0.5 - r, y + 0.5 - r) / r
            if d >= 1:
                return (0, 0, 0, 0)
            return (*mix(color, WHITE, max(0, 0.7 - d)), 255 * (1 - d) ** 1.6)
        return self._photo(size, size, rgba_bytes(size, size, pixel))

    def _star(self, size, brightness):
        r = size / 2
        c = mix((150, 170, 255), WHITE, brightness)

        def pixel(x, y):
            d = math.hypot(x + 0.5 - r, y + 0.5 - r) / r
            if d >= 1:
                return (0, 0, 0, 0)
            return (*c, 255 * brightness * (1 - d) ** 1.3)
        return self._photo(size, size, rgba_bytes(size, size, pixel))

    def background(self, w, h):
        """Fond : degrade vertical, nebuleuses colorees, vignette.

        Calcule en basse resolution puis agrandi : le fond est tres doux, on
        ne voit pas la difference et le demarrage reste instantane.
        """
        f = 4
        lw, lh = w // f + 1, h // f + 1
        nebulas = [
            (0.18, 0.25, 0.35, rgb("#3a1f7a"), 0.55),
            (0.85, 0.70, 0.40, rgb("#0f4a7a"), 0.45),
            (0.50, 1.05, 0.45, rgb("#5a1a5e"), 0.40),
        ]

        def pixel(x, y):
            u, v = x / lw, y / lh
            c = mix(BG_TOP, BG_BOTTOM, v)
            for nx, ny, nr, nc, na in nebulas:
                d2 = ((u - nx) ** 2 + (v - ny) ** 2) / (nr * nr)
                c = mix(c, nc, na * math.exp(-d2 * 2.2))
            vig = ((u - 0.5) ** 2 + (v - 0.5) ** 2) * 1.1
            c = mix(c, (0, 0, 0), min(0.6, vig))
            return (*c, 255)
        return self._photo(lw, lh, rgba_bytes(lw, lh, pixel)).zoom(f, f)

    def board_back(self, cols, rows, s):
        img = self.tk.PhotoImage(width=cols * s, height=rows * s)
        img.put(hexc(BOARD_BG), to=(0, 0, cols * s, rows * s))
        slot = hexc(SLOT)
        for r in range(rows):
            for c in range(cols):
                x0, y0 = c * s, r * s
                img.put(slot, to=(x0 + 1, y0 + 1, x0 + s - 1, y0 + s - 1))
        return img


# --------------------------------------------------------------------------
# Sons synthetises (Windows : winsound ; ailleurs, le jeu reste muet)
# --------------------------------------------------------------------------

RATE = 22050


def note(n):
    """Frequence d'une note, n = demi-tons depuis le La 440 Hz."""
    return 440.0 * 2 ** (n / 12)


C5, E5, G5, C6, E6, G6, C7 = (note(n) for n in (3, 7, 10, 15, 19, 22, 27))


def synth(parts, rng):
    """parts : (debut, duree, f_debut, f_fin, forme, volume)."""
    total = max(s + d for s, d, *_ in parts)
    buf = [0.0] * (int(total * RATE) + 2)
    for start, dur, f0, f1, shape, vol in parts:
        n = int(dur * RATE)
        i0 = int(start * RATE)
        phase = 0.0
        attack = 0.004 * RATE
        for i in range(n):
            t = i / n
            phase += (f0 + (f1 - f0) * t) / RATE
            p = phase % 1.0
            if shape == "sq":
                x = 0.6 if p < 0.5 else -0.6
            elif shape == "tri":
                x = 4 * abs(p - 0.5) - 1
            elif shape == "noise":
                x = rng.uniform(-1, 1)
            else:
                x = math.sin(2 * math.pi * p)
            env = min(1.0, i / attack) * (1 - t) ** 1.8
            buf[i0 + i] += x * vol * env
    # normalisation : chaque son culmine au meme volume, fort mais sans
    # saturer quand deux sons se superposent
    peak = max(abs(v) for v in buf) or 1.0
    gain = 0.5 * 32767 / peak
    return array("h", (int(v * gain) for v in buf))


def _arp(freqs, step, dur, shape="sq", vol=0.18, start=0.0):
    return [(start + i * step, dur, f, f, shape, vol) for i, f in enumerate(freqs)]


SOUNDS = {
    # nom : (volume relatif, parties)
    "rotate": (0.45, [(0, 0.07, 1100, 1500, "tri", 1)]),
    "hold": (0.6, [(0, 0.12, 750, 330, "sin", 1)]),
    "lock": (0.7, [(0, 0.1, 190, 90, "sin", 1), (0, 0.04, 0, 0, "noise", 0.15)]),
    "drop": (1.0, [(0, 0.16, 260, 50, "sin", 1), (0, 0.08, 0, 0, "noise", 0.3)]),
    "blip": (0.5, [(0, 0.08, 880, 880, "tri", 1)]),
    "clear1": (0.8, _arp([C6, G6], 0.05, 0.14)),
    "clear2": (0.85, _arp([C6, E6, G6], 0.045, 0.16)),
    "clear3": (0.9, _arp([C6, E6, G6, C7], 0.04, 0.18)),
    "tetris": (1.0, _arp([C5, E5, G5, C6, E6, G6, C7], 0.035, 0.18)
               + [(0.25, 0.45, C6, C6, "sq", 0.12), (0.25, 0.45, E6, E6, "tri", 0.2),
                  (0.25, 0.45, G6, G6, "tri", 0.2)]),
    "tspin": (1.0, _arp([G6, C7, G6, C7], 0.05, 0.1, "tri", 0.3)
              + [(0.2, 0.3, C7, C7 * 1.5, "sin", 0.2)]),
    "level": (1.0, _arp([C6, E6, G6], 0.08, 0.12)
              + [(0.24, 0.4, C7, C7, "sq", 0.14), (0.24, 0.4, G6, G6, "tri", 0.2)]),
    "count": (0.7, [(0, 0.12, 660, 660, "sq", 1)]),
    "go": (0.8, [(0, 0.35, 1320, 1320, "sq", 0.14), (0, 0.35, 990, 990, "tri", 0.2)]),
    "over": (1.0, _arp([G5, note(8), E5, note(3), note(0)], 0.14, 0.2, "tri", 0.3)
             + [(0.7, 0.5, 110, 70, "sin", 0.5)]),
}


class WaveOut:
    """Sortie audio Windows (winmm) pilotee par ctypes.

    Le peripherique est ouvert une seule fois. Un fil d'execution lui envoie
    en continu des blocs de 23 ms dans lesquels on mixe les sons en cours :
    aucun delai d'ouverture a chaque son, et plusieurs sons a la fois.
    """

    BLOCK = 512  # echantillons par bloc
    BUFFERS = 3
    WHDR_DONE = 1

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                        ("nSamplesPerSec", wintypes.DWORD),
                        ("nAvgBytesPerSec", wintypes.DWORD),
                        ("nBlockAlign", wintypes.WORD),
                        ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD)]

        class WAVEHDR(ctypes.Structure):
            pass
        WAVEHDR._fields_ = [("lpData", ctypes.c_void_p),
                            ("dwBufferLength", wintypes.DWORD),
                            ("dwBytesRecorded", wintypes.DWORD),
                            ("dwUser", ctypes.c_size_t), ("dwFlags", wintypes.DWORD),
                            ("dwLoops", wintypes.DWORD),
                            ("lpNext", ctypes.POINTER(WAVEHDR)),
                            ("reserved", ctypes.c_size_t)]

        self.ct = ctypes
        winmm = self.winmm = ctypes.WinDLL("winmm")
        winmm.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
                                      ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
                                      ctypes.c_size_t, wintypes.DWORD]
        for fn in (winmm.waveOutPrepareHeader, winmm.waveOutWrite):
            fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        self.handle = ctypes.c_void_p()
        fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        if winmm.waveOutOpen(ctypes.byref(self.handle), 0xFFFFFFFF,
                             ctypes.byref(fmt), 0, 0, 0) != 0:
            raise OSError("waveOutOpen a echoue")
        size = self.BLOCK * 2
        self.buffers = [ctypes.create_string_buffer(size) for _ in range(self.BUFFERS)]
        self.headers = []
        for buf in self.buffers:
            hdr = WAVEHDR()
            hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
            hdr.dwBufferLength = size
            if winmm.waveOutPrepareHeader(self.handle, ctypes.byref(hdr),
                                          ctypes.sizeof(hdr)) != 0:
                raise OSError("waveOutPrepareHeader a echoue")
            hdr.dwFlags |= self.WHDR_DONE  # libre, a remplir
            self.headers.append(hdr)
        self.voices = []
        self.lock = threading.Lock()
        self.blocks_played = 0
        self.silence = bytes(size)
        threading.Thread(target=self._run, daemon=True).start()

    def play(self, samples, volume):
        with self.lock:
            if len(self.voices) >= 6:
                self.voices.pop(0)
            self.voices.append([samples, 0, volume])

    def _mix(self) -> bytes:
        n = self.BLOCK
        with self.lock:
            voices = self.voices
            self.voices = []
            for v in voices:
                if v[1] + n < len(v[0]):
                    self.voices.append([v[0], v[1] + n, v[2]])
        if not voices:
            return self.silence
        out = [0] * n
        for samples, pos, vol in voices:
            for i, x in enumerate(samples[pos:pos + n]):
                out[i] += x * vol
        return array("h", (-32767 if x < -32767 else (32767 if x > 32767 else int(x))
                           for x in out)).tobytes()

    def _run(self):
        ct = self.ct
        while True:
            for hdr, buf in zip(self.headers, self.buffers):
                if hdr.dwFlags & self.WHDR_DONE:  # bloc joue : on le remplit
                    ct.memmove(buf, self._mix(), self.BLOCK * 2)
                    hdr.dwFlags &= ~self.WHDR_DONE
                    self.winmm.waveOutWrite(self.handle, ct.byref(hdr), ct.sizeof(hdr))
                    self.blocks_played += 1
            time.sleep(0.004)


class Sound:
    """Effets sonores synthetises au demarrage, joues sans bloquer le jeu.

    Sous Windows par WaveOut ; si la sortie audio ne s'ouvre pas, repli sur
    winsound (un son a la fois). Ailleurs, le jeu reste muet.
    """

    def __init__(self):
        self.muted = False
        self.ready = False
        self.sounds = {}
        self.files = {}
        self.out = None
        try:
            import winsound
        except ImportError:
            self.winsound = None
            return
        self.winsound = winsound
        threading.Thread(target=self._build, daemon=True).start()

    def _build(self):
        rng = random.Random(0)
        for name, (volume, parts) in SOUNDS.items():
            self.sounds[name] = (synth(parts, rng), volume)
        try:
            self.out = WaveOut()
        except (OSError, AttributeError):
            self._write_files()
        self.ready = True

    def _write_files(self):
        """Repli winsound : il lui faut des fichiers WAV sur le disque."""
        folder = Path(tempfile.gettempdir()) / "blocs_sons"
        try:
            folder.mkdir(exist_ok=True)
            for name, (samples, volume) in self.sounds.items():
                path = folder / f"{name}.wav"
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(RATE)
                    w.writeframes(array("h", (int(x * volume) for x in samples)).tobytes())
                self.files[name] = str(path)
        except OSError:
            self.files = {}

    def play(self, name):
        if self.muted or not self.ready or name not in self.sounds:
            return
        if self.out is not None:
            samples, volume = self.sounds[name]
            self.out.play(samples, volume)
        elif name in self.files:
            ws = self.winsound
            try:
                ws.PlaySound(self.files[name],
                             ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_NODEFAULT)
            except RuntimeError:
                pass


# --------------------------------------------------------------------------
# Calques : des reserves d'objets du canevas, reutilises a chaque image
# --------------------------------------------------------------------------


class ImageLayer:
    """Chaque image, on "declare" les sprites a afficher ; le calque ne
    touche au canevas que pour ce qui a vraiment change depuis l'image
    precedente. Creer et detruire des objets a chaque image serait lent."""

    def __init__(self, canvas, size, anchor="nw"):
        self.canvas = canvas
        self.items = [canvas.create_image(0, 0, anchor=anchor, state="hidden")
                      for _ in range(size)]
        self.state = [None] * size
        self.count = 0
        self.previous = 0

    def begin(self):
        self.count = 0

    def add(self, img, x, y):
        i = self.count
        if i >= len(self.items):
            return
        x, y = int(round(x)), int(round(y))
        old = self.state[i]
        item = self.items[i]
        if old is None:
            self.canvas.itemconfigure(item, image=img, state="normal")
            self.canvas.coords(item, x, y)
        else:
            if old[0] is not img:
                self.canvas.itemconfigure(item, image=img)
            if old[1] != x or old[2] != y:
                self.canvas.coords(item, x, y)
        self.state[i] = (img, x, y)
        self.count += 1

    def end(self):
        for i in range(self.count, self.previous):
            self.canvas.itemconfigure(self.items[i], state="hidden")
            self.state[i] = None
        self.previous = self.count


class TextLayer:
    def __init__(self, canvas, size):
        self.canvas = canvas
        self.items = [canvas.create_text(0, 0, state="hidden") for _ in range(size)]
        self.state = [None] * size
        self.count = 0
        self.previous = 0

    def begin(self):
        self.count = 0

    def add(self, text, x, y, color, font, anchor="center"):
        i = self.count
        if i >= len(self.items):
            return
        st = (text, int(x), int(y), color, font, anchor)
        if self.state[i] != st:
            item = self.items[i]
            self.canvas.itemconfigure(item, text=text, fill=color, font=font,
                                      anchor=anchor, state="normal")
            self.canvas.coords(item, int(x), int(y))
            self.state[i] = st
        self.count += 1

    def end(self):
        for i in range(self.count, self.previous):
            self.canvas.itemconfigure(self.items[i], state="hidden")
            self.state[i] = None
        self.previous = self.count


def round_rect(canvas, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
           x1, y0 + r, x1, y1 - r, x1, y1 - r, x1, y1, x1 - r, y1, x1 - r, y1,
           x0 + r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r,
           x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, **kw)


def fmt(n):
    return f"{int(n):,}".replace(",", " ")


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

DAS = 0.16  # delai avant la repetition d'un deplacement maintenu
ARR = 0.045  # intervalle de repetition
CLEAR_FLASH = 0.22  # disparition des lignes
CLEAR_FALL = 0.2  # chute des lignes du dessus
FPS = 120
GLOW_LAYERS = 12

KEYS = {
    "Left": "left", "Right": "right", "Down": "down",
    "Up": "cw", "x": "cw",
    "z": "ccw", "w": "ccw", "Control_L": "ccw", "Control_R": "ccw",
    "space": "drop", "Return": "start", "KP_Enter": "start",
    "c": "hold", "Shift_L": "hold", "Shift_R": "hold",
    "p": "pause", "Escape": "pause",
    "r": "restart", "q": "menu", "m": "mute", "f": "fps",
}

RECORD_FILE = Path(__file__).with_name(".blocs_record.json")

TITLE_FONT = {
    "B": ("XXXX.", "X...X", "XXXX.", "X...X", "XXXX."),
    "L": ("X....", "X....", "X....", "X....", "XXXXX"),
    "O": (".XXX.", "X...X", "X...X", "X...X", ".XXX."),
    "C": (".XXXX", "X....", "X....", "X....", ".XXXX"),
    "S": (".XXXX", "X....", ".XXX.", "....X", "XXXX."),
}
TITLE_COLORS = "ZLOSI"

LABELS = {1: "SIMPLE", 2: "DOUBLE", 3: "TRIPLE", 4: "TETRIS"}


def load_record() -> int:
    try:
        return int(json.loads(RECORD_FILE.read_text())["record"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def save_record(score: int):
    try:
        RECORD_FILE.write_text(json.dumps({"record": score}))
    except OSError:
        pass


class App:
    def __init__(self, root, level: int = 1, seed=None):
        import tkinter as tk

        self.root = root
        self.level = level
        self.seed = seed
        self.record = load_record()
        self.sound = Sound()
        self.rng = random.Random()

        self.scale = s = root.winfo_fpixels("1i") / 96
        screen_h = root.winfo_screenheight()
        c = self.cell = int(max(20, min(34 * s, (screen_h - 140 * s) / 22)))
        self.mini = int(c * 0.72)
        self.bx, self.by = 8 * c, c
        self.W, self.H = 26 * c, 22 * c
        self.lx, self.rx = c, 19 * c

        root.title("BLOCS")
        root.configure(bg=hexc(BG_TOP))
        root.resizable(False, False)
        cv = self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                     bg=hexc(BG_TOP), highlightthickness=0)
        cv.pack()

        self.f_label = ("Segoe UI Semibold", -int(c * 0.36))
        self.f_small = ("Segoe UI", -int(c * 0.34))
        self.f_num = ("Consolas", -int(c * 0.62), "bold")
        self.f_card = ("Segoe UI Black", -int(c * 0.72))

        # Ecran de chargement le temps de generer les images
        cv.create_text(self.W / 2, self.H / 2, text="BLOCS", fill=hexc(TEXT),
                       font=("Segoe UI Black", -int(c * 1.2)), tags="loading")
        root.update()
        self.assets = Assets(tk, c, self.mini, s)
        cv.delete("loading")

        self.bg_image = self.assets.background(self.W, self.H)
        cv.create_image(0, 0, image=self.bg_image, anchor="nw")
        self.stars = [[self.rng.uniform(0, self.W), self.rng.uniform(0, self.H),
                       self.rng.uniform(4, 22) * s, self.rng.randrange(3),
                       self.rng.uniform(0, 6.28)] for _ in range(90)]
        self.L_stars = ImageLayer(cv, 2 * len(self.stars), anchor="center")
        self.L_rain = ImageLayer(cv, 80)
        self._build_static()

        self.L_board = ImageLayer(cv, 230)
        self.L_ghost = ImageLayer(cv, 4)
        self.L_trail = ImageLayer(cv, 200)
        self.L_piece = ImageLayer(cv, 4)
        self.L_panel = ImageLayer(cv, 30)
        self.L_particles = ImageLayer(cv, 500, anchor="center")
        self.L_title = ImageLayer(cv, 100)
        self.T_pop = TextLayer(cv, 24)
        self._build_card()
        self.T_menu = TextLayer(cv, 16)
        self.fps_item = cv.create_text(self.W - 8, 8, anchor="ne", fill=hexc(MUTED),
                                       font=self.f_small, state="hidden")

        root.bind("<KeyPress>", self.on_press)
        root.bind("<KeyRelease>", self.on_release)
        root.bind("<FocusOut>", self.on_focus_out)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.held = {}
        self.pending_release = {}
        self.direction = None
        self.repeat_at = 0.0
        self.show_fps = False
        self.fps_frames = 0
        self.fps_t0 = time.perf_counter()
        self.particles = []
        self.popups = []
        self.trails = []
        self.bump = self.bump_v = 0.0
        self.shake = 0.0
        self.shake_applied = (0, 0)
        self.warp = 0.0
        self.theme = self.theme_target = THEMES[0]
        self.glow_boost = 0.0
        self.glow_sig = None
        self.go_menu()
        self.last = time.perf_counter()
        self.frame_id = root.after(0, self.frame)
        root.focus_force()

    # --- decor fixe -----------------------------------------------------

    def _build_static(self):
        cv, c = self.canvas, self.cell
        bx, by = self.bx, self.by
        bw, bh = WIDTH * c, (HEIGHT - HIDDEN) * c

        # halo du plateau : contours de plus en plus larges et pales
        # (chaque contour chevauche le suivant : pas de rayures entre eux)
        self.glow_items = []
        step = max(2, round(c * 0.045))
        for i in range(GLOW_LAYERS, 0, -1):
            pad = i * step
            item = round_rect(cv, bx - pad - 2, by - pad - 2, bx + bw + pad + 1,
                              by + bh + pad + 1, c * 0.2 + pad, fill="",
                              outline="#000000", width=step + 2,
                              tags=("ui", "boardfx"))
            self.glow_items.append((i, item))
        self.board_img = self.assets.board_back(WIDTH, HEIGHT - HIDDEN, c)
        cv.create_image(bx, by, image=self.board_img, anchor="nw",
                        tags=("ui", "boardfx"))

        edge = hexc(PANEL_EDGE)
        fill = hexc(PANEL)
        lx, rx, pw = self.lx, self.rx, 6 * c
        round_rect(cv, lx, by + 0.55 * c, lx + pw, by + 4.1 * c, c * 0.3,
                   fill=fill, outline=edge, width=2, tags="ui")
        round_rect(cv, rx, by + 0.55 * c, rx + pw, by + 13.1 * c, c * 0.3,
                   fill=fill, outline=edge, width=2, tags="ui")

        def label(x, y, text, anchor="nw"):
            cv.create_text(x, y, text=text, anchor=anchor, fill=hexc(MUTED),
                           font=self.f_label, tags="ui")

        label(lx + 2, by - 0.05 * c, "RÉSERVE")
        label(rx + 2, by - 0.05 * c, "SUIVANTES")
        stats = {}
        for name, y in (("SCORE", 4.9), ("RECORD", 6.9), ("NIVEAU", 8.9),
                        ("LIGNES", 11.3)):
            label(lx + 2, by + y * c, name)
            stats[name] = cv.create_text(lx + 2, by + (y + 0.45) * c, text="0",
                                         anchor="nw", fill=hexc(TEXT),
                                         font=self.f_num, tags="ui")
        for name, y in (("TEMPS", 13.8), ("PIÈCES", 15.8)):
            label(rx + 2, by + y * c, name)
            stats[name] = cv.create_text(rx + 2, by + (y + 0.45) * c, text="0",
                                         anchor="nw", fill=hexc(TEXT),
                                         font=self.f_num, tags="ui")
        self.stat_items = stats
        self.stat_cache = {}
        self.combo_item = cv.create_text(rx + 2, by + 18 * c, text="", anchor="nw",
                                         fill=hexc(GOLD), font=self.f_card, tags="ui")
        self.b2b_item = cv.create_text(rx + 2, by + 19.1 * c, text="", anchor="nw",
                                       fill=hexc(COLORS["T"]), font=self.f_label,
                                       tags="ui")

        # barre de progression vers le niveau suivant
        y = by + 10.55 * c
        self.bar_x0, self.bar_x1 = lx + 2, lx + pw - 2
        round_rect(cv, self.bar_x0, y, self.bar_x1, y + 0.28 * c, c * 0.14,
                   fill=hexc(SLOT), outline="", tags="ui")
        self.bar = round_rect(cv, self.bar_x0, y, self.bar_x0 + 1, y + 0.28 * c,
                              c * 0.14, fill="#ffffff", outline="", tags="ui")
        self.bar_y = y
        self.bar_shown = 0.0
        self.bar_sig = None

        help_lines = ("← →  déplacer    ↓  accélérer", "↑ X  tourner    W Z  ↺",
                      "Espace  lâcher    C  réserve", "P  pause    M  son    R  rejouer")
        for i, line in enumerate(help_lines):
            cv.create_text(lx + 2, by + (17.6 + i * 0.6) * c, text=line, anchor="nw",
                           fill=hexc(mix(MUTED, BG_BOTTOM, 0.25)), font=self.f_small,
                           tags="ui")

    def _build_card(self):
        cv, c = self.canvas, self.cell
        cx = self.bx + WIDTH * c / 2
        cy = self.by + (HEIGHT - HIDDEN) * c / 2
        self.card_items = [round_rect(cv, cx - 4.6 * c, cy - 2.9 * c, cx + 4.6 * c,
                                      cy + 2.9 * c, c * 0.4, fill=hexc(PANEL),
                                      outline=hexc(PANEL_EDGE), width=2,
                                      state="hidden")]
        self.card_title = cv.create_text(cx, cy - 1.6 * c, font=self.f_card,
                                         fill=hexc(TEXT), state="hidden")
        self.card_lines = [cv.create_text(cx, cy + (-0.35 + i * 0.8) * c,
                                          font=self.f_label, state="hidden")
                           for i in range(3)]
        self.card_items += [self.card_title] + self.card_lines
        self.card_sig = None

    # --- etats : menu, compte a rebours, partie, pause, fin -------------

    def go_menu(self):
        self.mode = "menu"
        self.mode_t0 = time.perf_counter()
        self.game = None
        self.canvas.itemconfigure("ui", state="hidden")
        self.set_card(None)
        self.popups.clear()
        self.particles.clear()
        self.trails.clear()
        self.rain = [self._rain_piece(initial=True) for _ in range(14)]

    def _rain_piece(self, initial=False):
        c = self.cell
        return [self.rng.choice(list(SHAPES)), self.rng.randrange(4),
                self.rng.uniform(-c, self.W), self.rng.uniform(-self.H, self.H)
                if initial else -4 * c, self.rng.uniform(0.6, 2.2) * c]

    def new_game(self):
        now = time.perf_counter()
        self.canvas.itemconfigure("ui", state="normal")
        self.game = Game(seed=self.seed, level=self.level)
        self.game.events.clear()
        self.mode = "countdown"
        self.mode_t0 = now
        self.count_step = -1
        self.play_time = 0.0
        self.shown_score = 0.0
        self.score_flash = 0.0
        self.clear_anim = None
        self.lock_flash = {}
        self.over_t0 = None
        self.hold_flash = 0.0
        self.queue_off = 0.0
        self.record_saved = False
        self.theme = THEMES[(self.level - 1) % len(THEMES)]
        self.theme_target = self.theme
        self.popups.clear()
        self.particles.clear()
        self.trails.clear()
        self.set_card(None)
        self.snap_piece()

    def snap_piece(self):
        g = self.game
        self.vis = [[float(x), float(y)] for x, y in g.cells()]
        self.piece_key = (g.kind, id(g), g.pieces)

    def set_card(self, content):
        if content == self.card_sig:
            return
        self.card_sig = content
        cv = self.canvas
        if content is None:
            for item in self.card_items:
                cv.itemconfigure(item, state="hidden")
            return
        title, lines = content
        for item in self.card_items:
            cv.itemconfigure(item, state="normal")
        cv.itemconfigure(self.card_title, text=title)
        for item, (text, color) in zip(self.card_lines, lines + [("", TEXT)] * 3):
            cv.itemconfigure(item, text=text, fill=hexc(color))

    # --- clavier --------------------------------------------------------

    @staticmethod
    def action(event):
        key = event.keysym if len(event.keysym) > 1 else event.keysym.lower()
        return KEYS.get(key)

    def on_press(self, event):
        a = self.action(event)
        if a is None:
            return
        # Linux envoie relachement + appui pour chaque repetition auto :
        # un appui juste apres un relachement annule ce relachement.
        if a in self.pending_release:
            self.root.after_cancel(self.pending_release.pop(a))
            return
        if a in self.held:  # repetition auto de Windows : deja gere
            return
        now = time.perf_counter()
        self.held[a] = now

        if a == "mute":
            self.sound.muted = not self.sound.muted
            return
        if a == "fps":
            self.show_fps = not self.show_fps
            self.canvas.itemconfigure(self.fps_item,
                                      state="normal" if self.show_fps else "hidden")
            return

        mode = self.mode
        if mode == "menu":
            if a in ("left", "right"):
                self.level = max(1, min(15, self.level + (1 if a == "right" else -1)))
                self.sound.play("blip")
            elif a in ("drop", "start"):
                self.sound.play("blip")
                self.new_game()
            return
        if a == "restart":
            self.new_game()
            return
        if mode == "over":
            if a in ("drop", "start") and now - self.over_t0 > 1.2:
                self.new_game()
            elif a in ("menu", "pause"):
                self.go_menu()
            return
        if mode == "paused":
            if a == "pause":
                self.mode = "play"
                self.sound.play("blip")
            elif a == "menu":
                self.go_menu()
            return
        if a == "pause":
            if mode == "play":
                self.mode = "paused"
                self.sound.play("blip")
            return
        if mode != "play":
            return

        g = self.game
        if a in ("left", "right"):
            self.direction = a
            g.move(-1 if a == "left" else 1)
            self.repeat_at = now + DAS
        elif a == "cw":
            g.rotate(1)
        elif a == "ccw":
            g.rotate(-1)
        elif a == "drop":
            g.hard_drop()
        elif a == "hold":
            g.hold()
        self.handle_events(now)

    def on_release(self, event):
        a = self.action(event)
        if a in self.held and a not in self.pending_release:
            self.pending_release[a] = self.root.after(25, lambda: self._release(a))

    def _release(self, a):
        self.pending_release.pop(a, None)
        self.held.pop(a, None)
        if a == self.direction:
            other = "right" if a == "left" else "left"
            if other in self.held:
                self.direction = other
                self.repeat_at = time.perf_counter() + DAS
            else:
                self.direction = None

    def on_focus_out(self, _event):
        for after_id in self.pending_release.values():
            self.root.after_cancel(after_id)
        self.pending_release.clear()
        self.held.clear()
        self.direction = None
        if self.mode == "play":
            self.mode = "paused"

    # --- evenements du jeu -> animations et sons -------------------------

    def handle_events(self, now):
        g = self.game
        events, g.events = g.events, []
        c = self.cell
        dropped = False
        for ev in events:
            kind = ev["type"]
            if kind == "rotate":
                self.sound.play("rotate")
            elif kind == "hold":
                self.sound.play("hold")
                self.hold_flash = now
                self.snap_piece()
            elif kind == "spawn":
                self.snap_piece()
                if ev["from_queue"]:
                    self.queue_off = 1.0
            elif kind == "harddrop":
                dropped = True
                self.trails.append((ev["kind"], ev["from"], ev["to"], now))
                self.bump_v += (6 + min(ev["rows"], 12)) * c * 0.9
                self.sound.play("drop")
                for cx, cy in ev["to"]:
                    if (cx, cy + 1) not in ev["to"]:
                        self._burst(self.bx + (cx + 0.5) * c,
                                    self.by + (cy - HIDDEN + 1) * c, "W", 3,
                                    speed=3.5, up=1.5, life=0.35, size=1)
            elif kind == "lock":
                for pos in ev["cells"]:
                    self.lock_flash[pos] = now
                if not dropped:
                    self.sound.play("lock")
                    self.bump_v += c * 1.6
            elif kind == "clear":
                self._on_clear(ev, now)
            elif kind == "level":
                self._on_level(ev["level"], now)
            elif kind == "over":
                self.mode = "over"
                self.over_t0 = now
                self.sound.play("over")
                self.shake = max(self.shake, 0.25 * c)
                if g.score > self.record:
                    self.record = g.score
                    save_record(g.score)
                    self.new_record = True
                else:
                    self.new_record = False

    def _on_clear(self, ev, now):
        c = self.cell
        n = ev["count"]
        cx = self.bx + WIDTH * c / 2
        if n:
            self.clear_anim = {"t0": now, "rows": set(ev["rows"]),
                               "before": ev["before"], "shift": ev["shift"],
                               "long": n == 4}
            self.lock_flash.clear()
            for r in ev["rows"]:
                for col in range(WIDTH):
                    k = ev["before"][r][col]
                    x = self.bx + (col + 0.5) * c
                    y = self.by + (r - HIDDEN + 0.5) * c
                    self._burst(x, y, k, 5 if n == 4 else 3, speed=5 + n,
                                up=4 + n, life=0.9, size=4, spread_x=(col - 4.5) * 0.9)
                    if n == 4:
                        self._burst(x, y, "W", 2, speed=9, up=7, life=0.7, size=2)
            ymid = self.by + (sum(ev["rows"]) / n - HIDDEN + 0.5) * c
        else:
            ymid = self.by + (self.game.y - HIDDEN + 1) * c

        label = LABELS.get(n, "")
        if ev["tspin"]:
            label = "T-SPIN " + label if n else "T-SPIN"
        if ev["b2b"]:
            label = "B2B " + label
        big = n == 4 or ev["tspin"]
        color = GOLD if n == 4 else (COLORS["T"] if ev["tspin"] else TEXT)
        if label.strip():
            self.popup(label, cx, ymid - 0.3 * c, color, 1.2 if big else 0.9,
                       dur=1.1, rise=1.6 * c)
        self.popup("+" + fmt(ev["points"]), cx, ymid + (1.1 if big else 0.8) * c, GOLD, 0.6,
                   dur=1.0, rise=1.4 * c, delay=0.05)
        if ev["combo"] > 0:
            self.popup(f"COMBO ×{ev['combo']}", cx, ymid + (1.9 if big else 1.6) * c, COLORS["I"],
                       0.5, dur=0.9, rise=1.2 * c, delay=0.1)
        if ev["perfect"]:
            self.popup("PERFECT", cx, self.by + 8 * c, GOLD, 1.6, dur=1.8, rise=c)
            self.popup("CLEAR", cx, self.by + 9.6 * c, GOLD, 1.6, dur=1.8, rise=c,
                       delay=0.1)

        self.score_flash = now
        self.glow_boost = min(1.0, self.glow_boost + 0.25 * max(n, 1))
        self.shake = max(self.shake, {0: 0.05, 1: 0.06, 2: 0.1, 3: 0.16, 4: 0.34}[n] * c)
        if n == 4 or ev["perfect"]:
            self.warp = 5.0
            self.sound.play("tetris")
        elif ev["tspin"]:
            self.warp = 2.5
            self.sound.play("tspin")
        elif n:
            self.sound.play(f"clear{n}")

    def _on_level(self, level, now):
        c = self.cell
        self.theme_target = THEMES[(level - 1) % len(THEMES)]
        self.glow_boost = 1.0
        self.warp = max(self.warp, 3.0)
        self.popup("NIVEAU", self.bx + WIDTH * c / 2, self.by + 4.4 * c, self.theme_target,
                   0.8, dur=1.6, rise=0.6 * c, delay=0.25)
        self.popup(str(level), self.bx + WIDTH * c / 2, self.by + 5.9 * c,
                   self.theme_target, 1.8, dur=1.6, rise=0.6 * c, delay=0.3)
        for i in range(40):
            x = self.bar_x0 + (self.bar_x1 - self.bar_x0) * i / 39
            self._burst(x, self.bar_y, "G", 1, speed=3, up=4, life=0.8, size=2)
        self.sound.play("level")

    def _burst(self, x, y, color, count, speed=5.0, up=4.0, life=0.8, size=4,
               spread_x=0.0):
        c = self.cell
        rnd = self.rng
        for _ in range(count):
            if len(self.particles) >= 480:
                return
            vx = (rnd.uniform(-1, 1) * speed + spread_x) * c
            vy = -rnd.uniform(0.2, 1.0) * up * c
            t = rnd.uniform(0.6, 1.0) * life
            self.particles.append([x, y, vx, vy, t, t, color,
                                   rnd.randint(max(0, size - 2), size)])

    def popup(self, text, x, y, color, size, dur=1.0, rise=40, delay=0.0):
        self.popups.append({"text": text, "x": x, "y": y, "color": color,
                            "size": size, "t0": time.perf_counter() + delay,
                            "dur": dur, "rise": rise})

    # --- boucle principale ----------------------------------------------

    def frame(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        self.update(now, dt)
        self.draw(now, dt)

        self.fps_frames += 1
        if now - self.fps_t0 >= 0.5:
            if self.show_fps:
                fps = self.fps_frames / (now - self.fps_t0)
                self.canvas.itemconfigure(self.fps_item, text=f"{fps:.0f} img/s")
            self.fps_frames = 0
            self.fps_t0 = now
        spent = time.perf_counter() - now
        self.frame_id = self.root.after(max(1, int((1 / FPS - spent) * 1000)), self.frame)

    def close(self):
        self.root.after_cancel(self.frame_id)
        self.root.destroy()

    def update(self, now, dt):
        c = self.cell
        # effets communs a tous les etats
        self.warp *= math.exp(-dt * 2.5)
        self.shake *= math.exp(-dt * 9)
        steps = max(1, math.ceil(dt / 0.004))  # petits pas : reste stable
        for _ in range(steps):
            h = dt / steps
            self.bump_v += (-900 * self.bump - 26 * self.bump_v) * h
            self.bump += self.bump_v * h
        self.glow_boost *= math.exp(-dt * 2.2)
        self.theme = mix(self.theme, self.theme_target, min(1, dt * 3))

        grav = 30 * c
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] > 0:
                p[3] += grav * dt
                p[2] *= math.exp(-dt * 1.5)
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                alive.append(p)
        self.particles = alive
        self.popups = [p for p in self.popups if now - p["t0"] < p["dur"]]
        self.trails = [t for t in self.trails if now - t[3] < 0.35]

        if self.mode == "countdown":
            step = int((now - self.mode_t0) / 0.5)
            if step != self.count_step:
                self.count_step = step
                cx = self.bx + WIDTH * c / 2
                cy = self.by + 9 * c
                if step < 3:
                    self.popup(str(3 - step), cx, cy, TEXT, 2.4, dur=0.5, rise=0)
                    self.sound.play("count")
                else:
                    self.popup("GO !", cx, cy, self.theme, 2.4, dur=0.7, rise=c)
                    self.sound.play("go")
                    self.mode = "play"
            return
        if self.mode != "play":
            return

        g = self.game
        self.play_time += dt
        if self.clear_anim:
            anim = self.clear_anim
            if now - anim["t0"] > CLEAR_FLASH + CLEAR_FALL:
                self.clear_anim = None
        if self.direction and now >= self.repeat_at:
            g.move(-1 if self.direction == "left" else 1)
            self.repeat_at = now + ARR
        if not self.clear_anim:  # la gravite attend la fin de l'animation
            g.tick(dt, soft="down" in self.held)
        self.handle_events(now)

    # --- dessin ---------------------------------------------------------

    def draw(self, now, dt):
        self.draw_stars(now, dt)
        if self.mode == "menu":
            self.draw_menu(now, dt)
            for layer in (self.L_board, self.L_ghost, self.L_trail, self.L_piece,
                          self.L_panel):
                layer.begin()
                layer.end()
            self.draw_particles()
            self.draw_popups(now)
            return
        self.L_rain.begin()
        self.L_rain.end()
        self.L_title.begin()
        self.L_title.end()
        self.T_menu.begin()
        self.T_menu.end()

        c = self.cell
        sh = self.shake
        ox = sh * math.sin(now * 71) * 0.8
        oy = sh * math.cos(now * 53) * 0.8 + self.bump
        dx, dy = int(ox) - self.shake_applied[0], int(oy) - self.shake_applied[1]
        if dx or dy:
            self.canvas.move("boardfx", dx, dy)
            self.shake_applied = (int(ox), int(oy))
        ox, oy = self.shake_applied

        self.draw_glow()
        self.draw_board(now, ox, oy)
        self.draw_piece(now, dt, ox, oy)
        self.draw_trails(now, ox, oy)
        self.draw_panels(now, dt)
        self.draw_particles()
        self.draw_popups(now)
        self.draw_card(now)

    def draw_stars(self, now, dt):
        L = self.L_stars
        L.begin()
        speed = 1 + self.warp * 6
        imgs = self.assets.stars
        for st in self.stars:
            st[1] += st[2] * speed * dt
            if st[1] > self.H + 4:
                st[1] = -4
                st[0] = self.rng.uniform(0, self.W)
            tw = 0.5 + 0.5 * math.sin(now * 1.7 + st[4])
            L.add(imgs[st[3] * 3 + min(2, int(tw * 3))], st[0], st[1])
            if self.warp > 0.8:  # etirement "hyperespace"
                L.add(imgs[st[3] * 3], st[0], st[1] - st[2] * self.warp * 0.4)
        L.end()

    def draw_glow(self):
        strength = 0.55 + 0.45 * self.glow_boost
        theme = self.theme
        sig = (hexc(theme), round(strength, 2))
        if sig == self.glow_sig:
            return
        self.glow_sig = sig
        near = mix(BG_TOP, BG_BOTTOM, 0.5)
        for i, item in self.glow_items:
            t = strength * (1 - (i - 1) / GLOW_LAYERS) ** 2.4
            self.canvas.itemconfigure(item, outline=hexc(mix(near, theme, t)))

    def draw_board(self, now, ox, oy):
        g, c, A = self.game, self.cell, self.assets
        L = self.L_board
        L.begin()
        bx, by = self.bx + ox, self.by + oy
        anim = self.clear_anim
        over_rows = -1
        if self.over_t0 is not None:
            over_rows = int((now - self.over_t0) / 0.9 * (HEIGHT - HIDDEN))

        if anim and now - anim["t0"] < CLEAR_FLASH:
            t = (now - anim["t0"]) / CLEAR_FLASH
            steps = A.SHRINK_STEPS
            for r in range(HIDDEN, HEIGHT):
                row = anim["before"][r]
                y = by + (r - HIDDEN) * c
                clearing = r in anim["rows"]
                for col in range(WIDTH):
                    k = row[col]
                    if not k:
                        continue
                    x = bx + col * c
                    if not clearing:
                        L.add(A.block[k][0], x, y)
                    elif t < 0.25:
                        L.add(A.block[k][A.FLASH_LEVELS - 1], x, y)
                    else:
                        start = abs(col - 4.5) / 5 * 0.45
                        p = clamp01(((t - 0.25) / 0.75 - start) / 0.55)
                        if p < 1:
                            L.add(A.shrink[min(steps - 1, int(p * steps))], x, y)
        else:
            fall = None
            if anim:
                fall = 1 - ease_out_back(clamp01((now - anim["t0"] - CLEAR_FLASH) / CLEAR_FALL))
            for r in range(HIDDEN, HEIGHT):
                row = g.board[r]
                yr = r - anim["shift"][r] * fall if fall is not None else r
                y = by + (yr - HIDDEN) * c
                greyed = over_rows >= 0 and (HEIGHT - 1 - r) < over_rows
                for col in range(WIDTH):
                    k = row[col]
                    if not k:
                        continue
                    if greyed:
                        img = A.grey
                    else:
                        lvl = 0
                        t0 = self.lock_flash.get((col, r))
                        if t0 is not None:
                            f = 1 - (now - t0) / 0.2
                            if f > 0:
                                lvl = int(f * (A.FLASH_LEVELS - 2)) + 1
                            else:
                                del self.lock_flash[(col, r)]
                        img = A.block[k][lvl]
                    L.add(img, bx + col * c, y)
        L.end()

    def draw_piece(self, now, dt, ox, oy):
        g, c, A = self.game, self.cell, self.assets
        Lg, Lp = self.L_ghost, self.L_piece
        Lg.begin()
        Lp.begin()
        if not g.over:
            bx, by = self.bx + ox, self.by + oy
            targets = g.cells()
            # chaque case glisse vers sa place : deplacements et rotations fluides
            a = 1 - math.exp(-dt * 38)
            for v, (tx, ty) in zip(self.vis, targets):
                v[0] += (tx - v[0]) * a
                v[1] += (ty - v[1]) * a
            gy = g.ghost_y() - g.y
            ghost = A.ghost[g.kind]
            for tx, ty in targets:
                if gy > 0 and ty + gy >= HIDDEN and (tx, ty + gy) not in targets:
                    Lg.add(ghost, bx + tx * c, by + (ty + gy - HIDDEN) * c)
            lvl = 0
            if g.grounded() and self.mode == "play":
                # la piece s'eclaire a mesure que le verrouillage approche
                lvl = min(A.FLASH_LEVELS - 2, int(g.lock_timer / LOCK_DELAY * 3.5))
            img = A.block[g.kind][lvl]
            for vx, vy in self.vis:
                if vy > HIDDEN - 0.6:
                    Lp.add(img, bx + vx * c, by + (vy - HIDDEN) * c)
        Lg.end()
        Lp.end()

    def draw_trails(self, now, ox, oy):
        c, A = self.cell, self.assets
        L = self.L_trail
        L.begin()
        for kind, start, end, t0 in self.trails:
            fade = 1 - (now - t0) / 0.35
            imgs = A.trail[kind]
            cols = {}
            for (x, y0), (_, y1) in zip(start, end):
                top, bot = cols.get(x, (99, -1))
                cols[x] = (min(top, y0), max(bot, y1))
            ends = {}
            for x, y in end:
                ends[x] = min(ends.get(x, 99), y)
            for x, (top, _) in cols.items():
                bottom = ends[x]
                length = bottom - top
                for y in range(max(top, HIDDEN), bottom):
                    pos = (y - top + 1) / max(1, length)
                    lvl = int(fade * pos * len(imgs))
                    if lvl > 0:
                        L.add(imgs[min(lvl, len(imgs)) - 1], self.bx + ox + x * c,
                              self.by + oy + (y - HIDDEN) * c)
        L.end()

    def draw_panels(self, now, dt):
        g, c, A = self.game, self.cell, self.assets
        L = self.L_panel
        L.begin()
        m = self.mini

        def piece(kind, cx, cy, imgs_or_img, size):
            cells = ROTATIONS[kind][0]
            xs = [x for x, _ in cells]
            ys = [y for _, y in cells]
            x0 = cx - (max(xs) + min(xs) + 1) * size / 2
            y0 = cy - (max(ys) + min(ys) + 1) * size / 2
            for x, y in cells:
                L.add(imgs_or_img, x0 + x * size, y0 + y * size)

        if g.hold_kind:
            if g.hold_used:
                img = A.mini_grey
            else:
                f = 1 - (now - self.hold_flash) / 0.25
                img = A.mini[g.hold_kind][2 if f > 0.5 else (1 if f > 0 else 0)]
            piece(g.hold_kind, self.lx + 3 * c, self.by + 2.35 * c, img, m)

        self.queue_off *= math.exp(-dt * 14)
        off = self.queue_off
        for i, kind in enumerate(g.queue):
            pos = i + off
            if pos > 4.3:  # la derniere piece n'entre qu'une fois la place libre
                continue
            y = 2.45 + pos * 2.75 if pos < 1 else 5.2 + (pos - 1) * 2.1
            if pos < 0.5:
                piece(kind, self.rx + 3 * c, self.by + y * c, A.block[kind][0], c)
            else:
                piece(kind, self.rx + 3 * c, self.by + y * c, A.mini[kind][0], m)
        L.end()

        # chiffres : le score defile au lieu de sauter
        self.shown_score += (g.score - self.shown_score) * min(1, dt * 9)
        if abs(g.score - self.shown_score) < 1:
            self.shown_score = g.score
        flash = clamp01(1 - (now - self.score_flash) / 0.5)
        mins, secs = divmod(int(self.play_time), 60)
        values = {
            "SCORE": (fmt(self.shown_score), mix(TEXT, GOLD, flash)),
            "RECORD": (fmt(max(self.record, g.score)), TEXT),
            "NIVEAU": (str(g.level), self.theme),
            "LIGNES": (str(g.lines), TEXT),
            "TEMPS": (f"{mins}:{secs:02d}", TEXT),
            "PIÈCES": (str(g.pieces), TEXT),
        }
        for name, (text, color) in values.items():
            sig = (text, hexc(color))
            if self.stat_cache.get(name) != sig:
                self.stat_cache[name] = sig
                self.canvas.itemconfigure(self.stat_items[name], text=text, fill=sig[1])
        combo = f"COMBO ×{g.combo}" if g.combo > 0 else ""
        b2b = "BACK-TO-BACK" if g.b2b_ready else ""
        if self.stat_cache.get("combo") != (combo, b2b):
            self.stat_cache["combo"] = (combo, b2b)
            self.canvas.itemconfigure(self.combo_item, text=combo)
            self.canvas.itemconfigure(self.b2b_item, text=b2b)

        goal = (g.lines - (g.level - g.start_level) * 10) / 10
        self.bar_shown += (goal - self.bar_shown) * min(1, dt * 8)
        if goal < self.bar_shown - 0.5:  # passage de niveau : la barre repart
            self.bar_shown = goal
        x1 = self.bar_x0 + max(self.cell * 0.28, (self.bar_x1 - self.bar_x0) * self.bar_shown)
        sig = (int(x1), hexc(self.theme))
        if sig != self.bar_sig:
            self.bar_sig = sig
            r, y0, y1 = self.cell * 0.14, self.bar_y, self.bar_y + self.cell * 0.28
            x0 = self.bar_x0
            self.canvas.coords(self.bar, x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0,
                               x1, y0, x1, y0 + r, x1, y0 + r, x1, y1 - r, x1, y1 - r,
                               x1, y1, x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1,
                               x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r, x0, y0 + r,
                               x0, y0)
            self.canvas.itemconfigure(self.bar, fill=sig[1])

    def draw_particles(self):
        L = self.L_particles
        L.begin()
        dots = self.assets.dots
        for x, y, _, _, life, total, color, size in self.particles:
            idx = min(size, int(size * (life / total) + 0.999))
            L.add(dots[color][idx], x, y)
        L.end()

    def draw_popups(self, now):
        T = self.T_pop
        T.begin()
        c = self.cell
        shadow = hexc((0, 0, 0))
        for p in self.popups:
            t = (now - p["t0"]) / p["dur"]
            if t < 0:
                continue
            pop = ease_out_back(clamp01(t * 5))
            size = max(4, int(p["size"] * c * (0.4 + 0.6 * pop)))
            fade = clamp01((t - 0.65) / 0.35)
            color = hexc(mix(p["color"], mix(BG_TOP, BG_BOTTOM, 0.5), fade))
            y = p["y"] - p["rise"] * ease_out(t)
            font = ("Segoe UI Black", -size)
            if fade < 0.6:
                off = max(1, size // 14)
                T.add(p["text"], p["x"] + off, y + off, shadow, font)
            T.add(p["text"], p["x"], y, color, font)
        T.end()

    def draw_card(self, now):
        g = self.game
        if self.mode == "paused":
            self.set_card(("PAUSE", [("P  reprendre", TEXT), ("R  recommencer", MUTED),
                                     ("Q  menu      M  son", MUTED)]))
        elif self.mode == "over" and now - self.over_t0 > 1.0:
            best = ("NOUVEAU RECORD !", GOLD) if self.new_record and g.score else \
                (f"record  {fmt(self.record)}", MUTED)
            self.set_card(("PARTIE TERMINÉE", [(f"score  {fmt(g.score)}", TEXT), best,
                                               ("Espace  rejouer    Q  menu", MUTED)]))
        else:
            self.set_card(None)

    def draw_menu(self, now, dt):
        c, A = self.cell, self.assets
        t = now - self.mode_t0

        R = self.L_rain
        R.begin()
        m = self.mini
        for p in self.rain:
            p[3] += p[4] * dt
            if p[3] > self.H + m:
                p[:] = self._rain_piece()
            for x, y in ROTATIONS[p[0]][p[1]]:
                R.add(A.mini_dim[p[0]], p[2] + x * m, p[3] + y * m)
        R.end()

        L = self.L_title
        L.begin()
        width = len("BLOCS") * 6 - 1
        x0 = (self.W - width * m) / 2
        y0 = self.H * 0.26
        for li, letter in enumerate("BLOCS"):
            imgs = A.mini[TITLE_COLORS[li]]
            for row, line in enumerate(TITLE_FONT[letter]):
                for col, ch in enumerate(line):
                    if ch != "X":
                        continue
                    delay = li * 0.12 + (4 - row) * 0.05 + col * 0.015
                    p = clamp01((t - delay) / 0.75)
                    if p <= 0:
                        continue
                    fall = (1 - ease_out_bounce(p)) * (y0 + 6 * m)
                    wave_y = math.sin(now * 2.2 - (li * 6 + col) * 0.25) * m * 0.12 \
                        if p >= 1 else 0
                    shine = int((math.sin(now * 3 - (li * 6 + col) * 0.35) + 1) * 0.5
                                * 2.99) if p >= 1 else 0
                    shine = shine if shine == 2 else 0
                    L.add(imgs[shine], x0 + (li * 6 + col) * m,
                          y0 + row * m - fall + wave_y)
        L.end()

        T = self.T_menu
        T.begin()
        cx = self.W / 2
        fade = clamp01((t - 1.0) / 0.6)
        if fade > 0:
            muted = hexc(mix(BG_TOP, MUTED, fade))
            T.add("un jeu de blocs, en Python pur", cx, y0 + 6.2 * m, muted, self.f_label)
            pulse = 0.55 + 0.45 * math.sin(now * 3.2)
            T.add("ESPACE  pour jouer", cx, self.H * 0.6,
                  hexc(mix(BG_TOP, TEXT, fade * pulse)), ("Segoe UI Black", -int(c * 0.6)))
            T.add(f"◀   NIVEAU {self.level}   ▶", cx, self.H * 0.6 + 1.2 * c,
                  hexc(mix(BG_TOP, THEMES[(self.level - 1) % len(THEMES)], fade)),
                  self.f_card)
            if self.record:
                T.add(f"record  {fmt(self.record)}", cx, self.H * 0.6 + 2.3 * c,
                      muted, self.f_label)
            T.add("← →  déplacer   ↑  tourner   Espace  lâcher   C  réserve   "
                  "M  son", cx, self.H - 1.2 * c, muted, self.f_small)
        T.end()


def main():
    parser = argparse.ArgumentParser(description="BLOCS, un jeu de blocs qui tombent.")
    parser.add_argument("--niveau", type=int, default=1, help="niveau de départ (1 à 15)")
    parser.add_argument("--seed", type=int, default=None, help="rejouer le même tirage")
    args = parser.parse_args()

    import tkinter as tk

    try:  # sous Windows, evite une fenetre floue quand l'affichage est zoome
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError, OSError):
        pass

    root = tk.Tk()
    App(root, level=max(1, min(args.niveau, 15)), seed=args.seed)
    root.mainloop()


if __name__ == "__main__":
    main()
