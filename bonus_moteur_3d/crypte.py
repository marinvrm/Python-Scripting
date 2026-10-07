#!/usr/bin/env python3
"""CRYPTE : un moteur 3D temps reel qui tourne dans le terminal.

Un seul fichier, zero dependance : uniquement la bibliotheque standard.

Le rendu utilise du lancer de rayons (raycasting facon Wolfenstein 3D) :
pour chaque colonne de l'ecran on tire un rayon dans la grille du labyrinthe
avec l'algorithme DDA, on mesure la distance au mur touche, et on en deduit
la hauteur de la colonne a dessiner. Les textures sont generees par le code
(aucune image n'est chargee).

L'image est envoyee au terminal avec le caractere demi-bloc U+2580 : chaque
cellule du terminal affiche deux pixels (couleur de texte = pixel du haut,
couleur de fond = pixel du bas). On double ainsi la resolution verticale et
on obtient une vraie image en 16 millions de couleurs.

Commandes :
    Z/W, S       avancer / reculer
    Q/A, D       pas de cote
    fleches      tourner
    ESPACE       tirer
    ECHAP, X     quitter

Usage :
    python crypte.py                    # jouer
    python crypte.py --bench 200        # mesurer les FPS, sans affichage
    python crypte.py --capture vue.png  # exporter une image du moteur
    python crypte.py --size 100x60      # forcer la resolution
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import sys
import time
from collections import deque

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty


# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------

TEX = 64  # cote des textures de mur, en pixels
SPR = 32  # cote des sprites
SHADES = 24  # nombre de niveaux d'eclairage precalcules
FOG = 15.0  # distance a laquelle un mur devient noir
FOV = 0.66  # demi-largeur du plan camera (~66 degres)

MOVE_SPEED = 3.4
STRAFE_SPEED = 2.6
TURN_SPEED = 2.8
KEY_HOLD = 0.22  # duree pendant laquelle une touche reste "enfoncee"

MAZE = 25  # cote du labyrinthe, en cellules (doit etre impair)
ENEMIES = 6
SHOT_COOLDOWN = 0.32
SHOT_RANGE = 14.0
SHOT_APERTURE = 0.982  # cosinus de l'angle de tir
ENEMY_SPEED = 1.15
ENEMY_DAMAGE = 45.0  # points de vie par seconde au contact
TARGET_FPS = 45.0

UP = "\x1b[?25l"  # masquer le curseur
DOWN = "\x1b[?25h"  # reafficher le curseur


# --------------------------------------------------------------------------
# Textures et sprites generes par le code
# --------------------------------------------------------------------------


def _clamp(value: int) -> int:
    """Ramene une composante de couleur dans l'intervalle 0-255."""
    return 0 if value < 0 else (255 if value > 255 else value)


def _tint(rgb, factor: float, noise: int = 0):
    """Eclaircit ou assombrit une couleur, avec un grain optionnel."""
    r, g, b = rgb
    return (
        _clamp(int(r * factor) + noise),
        _clamp(int(g * factor) + noise),
        _clamp(int(b * factor) + noise),
    )


def _brick_texture(rnd: random.Random):
    """Mur de briques : rangees decalees, joints de mortier, grain."""
    columns = []
    tints = [0.82 + rnd.random() * 0.36 for _ in range(256)]
    for x in range(TEX):
        column = []
        for y in range(TEX):
            row = y // 16
            offset = (row % 2) * 16
            joint = ((x + offset) % 32) < 2 or (y % 16) < 2
            if joint:
                column.append(_tint((124, 118, 108), 1.0, rnd.randint(-10, 10)))
            else:
                brick = tints[(row * 7 + (x + offset) // 32 * 13) % 256]
                column.append(_tint((156, 66, 48), brick, rnd.randint(-8, 8)))
        columns.append(tuple(column))
    return columns


def _stone_texture(rnd: random.Random, hue=(118, 116, 122)):
    """Pierre taillee : blocs irreguliers separes par des fissures."""
    columns = []
    blocks = [0.78 + rnd.random() * 0.44 for _ in range(64)]
    for x in range(TEX):
        column = []
        for y in range(TEX):
            bx, by = x // 16, y // 8
            crack = (x % 16) < 1 or (y % 8) < 1
            if crack:
                column.append(_tint(hue, 0.42, rnd.randint(-6, 6)))
            else:
                column.append(
                    _tint(hue, blocks[(bx * 11 + by * 5) % 64], rnd.randint(-12, 12))
                )
        columns.append(tuple(column))
    return columns


def _moss_texture(rnd: random.Random):
    """Pierre envahie de mousse : des taches vertes fondues dans la pierre."""
    stone = _stone_texture(random.Random(rnd.random()), hue=(104, 108, 100))
    centres = [(rnd.randrange(TEX), rnd.randrange(TEX), 4.0 + rnd.random() * 5.0)
               for _ in range(9)]
    columns = []
    for x in range(TEX):
        column = []
        for y in range(TEX):
            r, g, b = stone[x][y]
            for cx, cy, radius in centres:
                distance = math.hypot(x - cx, y - cy)
                if distance < radius:
                    # fondu progressif vers le bord de la tache
                    k = (1.0 - distance / radius) * 0.75
                    r = int(r * (1.0 - k) + 38 * k)
                    g = int(g * (1.0 - k) + 122 * k)
                    b = int(b * (1.0 - k) + 44 * k)
                    break
            column.append((_clamp(r), _clamp(g), _clamp(b)))
        columns.append(tuple(column))
    return columns


def _rune_texture(rnd: random.Random):
    """Paroi sombre parcourue de runes lumineuses : le mur de la sortie."""
    columns = []
    glyphs = {(rnd.randrange(4, TEX - 4), rnd.randrange(4, TEX - 4))
              for _ in range(26)}
    for x in range(TEX):
        column = []
        for y in range(TEX):
            base = _tint((34, 38, 58), 1.0, rnd.randint(-6, 6))
            if (x % 32) < 2 or (y % 32) < 2:
                base = (58, 66, 96)
            for gx, gy in glyphs:
                if abs(x - gx) + abs(y - gy) < 3:
                    base = (90, 232, 214)
                    break
            column.append(base)
        columns.append(tuple(column))
    return columns


def build_textures():
    """Construit les quatre textures de mur du jeu."""
    rnd = random.Random(20260923)
    return [
        _brick_texture(rnd),
        _stone_texture(rnd),
        _moss_texture(rnd),
        _rune_texture(rnd),
    ]


def _flagstone_floor(rnd: random.Random):
    """Sol en dalles. Renvoie une liste plate de TEX*TEX pixels.

    Le format plat permet d'adresser un texel avec un simple decalage
    binaire pendant la projection du sol, ou chaque cycle compte.
    """
    pixels = []
    tons = [0.80 + rnd.random() * 0.40 for _ in range(64)]
    for y in range(TEX):
        for x in range(TEX):
            joint = (x % 21) < 2 or (y % 21) < 2
            if joint:
                pixels.append(_tint((58, 54, 50), 1.0, rnd.randint(-5, 5)))
            else:
                dalle = tons[((x // 21) * 7 + (y // 21) * 11) % 64]
                pixels.append(_tint((104, 96, 86), dalle, rnd.randint(-9, 9)))
    return pixels


def _rock_ceiling(rnd: random.Random):
    """Voute rocheuse sombre, en liste plate elle aussi."""
    pixels = []
    for y in range(TEX):
        for x in range(TEX):
            grain = math.sin(x * 0.4) * math.sin(y * 0.33) * 0.16
            pixels.append(_tint((46, 46, 58), 0.9 + grain, rnd.randint(-7, 7)))
    return pixels


def _ghost_sprite():
    """Un spectre : silhouette encapuchonnee, yeux lumineux, bas effiloche.

    Les pixels a None sont transparents.
    """
    rnd = random.Random(7)
    columns = []
    for x in range(SPR):
        column = []
        for y in range(SPR):
            pixel = None
            dx, dy = x - 15.5, y - 9.0
            if dx * dx + dy * dy < 48:  # la tete
                shade = 0.72 + 0.28 * (1.0 - (dx * dx + dy * dy) / 48.0)
                pixel = _tint((208, 214, 236), shade, rnd.randint(-6, 6))
            if y >= 12:  # le corps, qui s'evase vers le bas
                half = 5.0 + (y - 12) * 0.52
                # le bas de la robe est effiloche par une ondulation
                bas = 30.0
                if y > 25:
                    bas -= abs(1.4 * math.sin(x * 0.9 + y * 0.35))
                if abs(dx) < half and y < bas:
                    shade = 0.80 - (y - 12) * 0.016 - abs(dx) * 0.020
                    pixel = _tint((186, 196, 224), max(0.22, shade),
                                  rnd.randint(-5, 5))
            if 7 <= y <= 9 and (12 <= x <= 13 or 18 <= x <= 19):  # les yeux
                pixel = (120, 255, 236)
            column.append(pixel)
        columns.append(tuple(column))
    return columns


def _portal_sprite():
    """La sortie : un halo vert concentrique."""
    columns = []
    for x in range(SPR):
        column = []
        for y in range(SPR):
            dx, dy = x - 15.5, y - 15.5
            dist = math.hypot(dx, dy)
            if dist > 15.0:
                column.append(None)
                continue
            ring = 0.5 + 0.5 * math.sin(dist * 1.5)
            fade = 1.0 - dist / 15.0
            column.append((
                _clamp(int(40 * ring * fade)),
                _clamp(int((150 + 105 * ring) * fade)),
                _clamp(int((90 + 60 * ring) * fade)),
            ))
        columns.append(tuple(column))
    return columns


# --------------------------------------------------------------------------
# Labyrinthe
# --------------------------------------------------------------------------


def generate_maze(size: int, rnd: random.Random):
    """Genere un labyrinthe parfait par backtracking, puis ouvre des boucles.

    Retourne (grille, carte_des_textures). Dans la grille, 1 = mur, 0 = sol.
    """
    grid = [[1] * size for _ in range(size)]
    stack = [(1, 1)]
    grid[1][1] = 0
    while stack:
        x, y = stack[-1]
        voisins = []
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 0 < nx < size - 1 and 0 < ny < size - 1 and grid[ny][nx] == 1:
                voisins.append((nx, ny, dx, dy))
        if not voisins:
            stack.pop()
            continue
        nx, ny, dx, dy = rnd.choice(voisins)
        grid[y + dy // 2][x + dx // 2] = 0
        grid[ny][nx] = 0
        stack.append((nx, ny))

    # Un labyrinthe parfait est etouffant : on perce quelques murs au hasard
    # pour creer des boucles et rendre la navigation plus agreable.
    for _ in range(size * size // 12):
        x, y = rnd.randrange(2, size - 2), rnd.randrange(2, size - 2)
        if grid[y][x] == 1 and (grid[y][x - 1] == 0) != (grid[y - 1][x] == 0):
            grid[y][x] = 0

    textures = [[0] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            if x >= size - 6 and y >= size - 6:
                textures[y][x] = 3  # les runes, autour de la sortie
            else:
                textures[y][x] = (x * 7 + y * 13) % 3
    return grid, textures


def open_cells(grid):
    """Liste toutes les cellules praticables du labyrinthe."""
    return [(x, y)
            for y in range(len(grid))
            for x in range(len(grid)) if grid[y][x] == 0]


# --------------------------------------------------------------------------
# Clavier non bloquant
# --------------------------------------------------------------------------


class KeyReader:
    """Lit le clavier sans bloquer et simule des touches maintenues.

    Un terminal ne signale pas le relachement d'une touche : on considere
    donc qu'une touche reste enfoncee pendant KEY_HOLD secondes apres le
    dernier appui. La repetition automatique du clavier fait le reste et le
    deplacement parait continu.
    """

    ARROWS_NT = {b"K": "left", b"M": "right", b"H": "up", b"P": "down"}
    ARROWS_POSIX = {b"D": "left", b"C": "right", b"A": "up", b"B": "down"}

    def __init__(self):
        self.held = {}
        # Bornee : les touches de deplacement sont lues via held() et personne
        # ne vient jamais consommer leurs evenements. Sans maxlen, la file
        # grossirait pendant toute la partie.
        self.events = deque(maxlen=64)
        self._saved = None

    def __enter__(self):
        if os.name != "nt":
            self._saved = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *exc):
        if self._saved is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved)

    def poll(self, now: float) -> None:
        """Met a jour les touches maintenues et la file d'evenements."""
        for key in self._read():
            self.held[key] = now + KEY_HOLD
            self.events.append(key)
        for key in [k for k, expiry in self.held.items() if expiry <= now]:
            del self.held[key]

    def down(self, *keys) -> bool:
        """Vrai si l'une des touches est consideree comme enfoncee."""
        return any(k in self.held for k in keys)

    def take(self, key: str) -> bool:
        """Consomme un evenement ponctuel (tir, sortie de menu...)."""
        if key in self.events:
            self.events = deque((k for k in self.events if k != key), 64)
            return True
        return False

    def clear(self) -> None:
        self.events.clear()
        self.held.clear()

    def _read(self):
        return self._read_nt() if os.name == "nt" else self._read_posix()

    def _read_nt(self):
        keys = []
        while msvcrt.kbhit():
            char = msvcrt.getch()
            if char in (b"\x00", b"\xe0"):
                if msvcrt.kbhit():
                    arrow = self.ARROWS_NT.get(msvcrt.getch())
                    if arrow:
                        keys.append(arrow)
                continue
            keys.append(self._name(char))
        return [k for k in keys if k]

    def _read_posix(self):
        if not select.select([sys.stdin], [], [], 0)[0]:
            return []
        data = os.read(sys.stdin.fileno(), 256)
        keys, i = [], 0
        while i < len(data):
            char = data[i:i + 1]
            if char == b"\x1b" and data[i + 1:i + 2] == b"[":
                arrow = self.ARROWS_POSIX.get(data[i + 2:i + 3])
                if arrow:
                    keys.append(arrow)
                i += 3
                continue
            keys.append(self._name(char))
            i += 1
        return [k for k in keys if k]

    @staticmethod
    def _name(char: bytes):
        if char == b" ":
            return "space"
        if char == b"\x1b":
            return "esc"
        if char in (b"\r", b"\n"):
            return "enter"
        try:
            return char.decode("ascii").lower()
        except UnicodeDecodeError:
            return None


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------


class Renderer:
    """Transforme l'etat du jeu en une image, puis en sequence ANSI.

    L'image est construite colonne par colonne (c'est l'ordre naturel du
    lancer de rayons), puis transposee d'un coup avec zip() avant d'etre
    envoyee au terminal.
    """

    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height if height % 2 == 0 else height - 1
        self.textures = build_textures()
        self.sprites = [_ghost_sprite(), _portal_sprite()]
        rnd = random.Random(4242)
        self.planes = [_flagstone_floor(rnd), _rock_ceiling(rnd)]
        self._wall_cache = {}
        self._sprite_cache = {}
        self._plane_cache = {}
        self._span_cache = {}

    # -- caches -------------------------------------------------------------

    def plane_texture(self, which: int, level: int):
        """Texture plate de sol ou de plafond, pre-assombrie, en cache."""
        key = (which, level)
        flat = self._plane_cache.get(key)
        if flat is None:
            factor = level / (SHADES - 1)
            flat = [(int(r * factor), int(g * factor), int(b * factor))
                    for r, g, b in self.planes[which]]
            self._plane_cache[key] = flat
        return flat

    def wall_column(self, tex: int, tx: int, level: int):
        """Colonne de texture pre-assombrie, gardee en cache."""
        key = (tex, tx, level)
        column = self._wall_cache.get(key)
        if column is None:
            factor = level / (SHADES - 1)
            column = [(int(r * factor), int(g * factor), int(b * factor))
                      for r, g, b in self.textures[tex][tx]]
            self._wall_cache[key] = column
        return column

    def sprite_column(self, sprite: int, tx: int, level: int):
        """Idem pour les sprites, en preservant la transparence."""
        key = (sprite, tx, level)
        column = self._sprite_cache.get(key)
        if column is None:
            factor = level / (SHADES - 1)
            column = [None if p is None else
                      (int(p[0] * factor), int(p[1] * factor), int(p[2] * factor))
                      for p in self.sprites[sprite][tx]]
            self._sprite_cache[key] = column
        return column

    def span(self, line_h: int):
        """Pour une hauteur de mur donnee, renvoie (debut, fin, y_texture).

        Le resultat ne depend que de line_h : on le met donc en cache, ce qui
        supprime la boucle par pixel dans le cas general.
        """
        cached = self._span_cache.get(line_h)
        if cached is None:
            top = (self.h - line_h) // 2
            start = max(0, top)
            end = min(self.h, top + line_h)
            step = TEX / line_h
            ymap = [min(TEX - 1, int((y - top) * step)) for y in range(start, end)]
            cached = (start, end, ymap)
            self._span_cache[line_h] = cached
        return cached

    # -- sol et plafond -----------------------------------------------------

    def background(self, game):
        """Projette le sol et le plafond en perspective, ligne par ligne.

        Sur une ligne d'ecran donnee, tous les points du sol sont a la meme
        distance du joueur : on calcule cette distance une fois, puis on
        avance dans la texture par pas constants. Le plafond etant a la meme
        hauteur que le sol, la ligne symetrique se deduit gratuitement.
        """
        w, h = self.w, self.h
        half = h // 2
        px, py = game.px, game.py
        dx, dy = game.dir_x, game.dir_y
        plane_x, plane_y = -dy * FOV, dx * FOV
        left_x, left_y = dx - plane_x, dy - plane_y
        right_x, right_y = dx + plane_x, dy + plane_y
        span_x = (right_x - left_x) / w
        span_y = (right_y - left_y) / w
        flicker = game.flicker
        scale = 0.5 * h
        rows = [None] * h

        for y in range(half, h):
            distance = scale / (y - half + 0.5)
            step_x = distance * span_x
            step_y = distance * span_y
            fx = px + distance * left_x
            fy = py + distance * left_y

            light = flicker * (1.0 - distance / FOG)
            level = int((0.04 + 0.96 * (light if light > 0.0 else 0.0))
                        * (SHADES - 1))
            if level < 0:
                level = 0
            elif level >= SHADES:
                level = SHADES - 1
            floor_tex = self.plane_texture(0, level)
            ceil_tex = self.plane_texture(1, level)

            floor_row = []
            ceil_row = []
            add_floor = floor_row.append
            add_ceil = ceil_row.append
            for _ in range(w):
                texel = ((int(fy * TEX) & 63) << 6) | (int(fx * TEX) & 63)
                add_floor(floor_tex[texel])
                add_ceil(ceil_tex[texel])
                fx += step_x
                fy += step_y
            rows[y] = floor_row
            rows[h - 1 - y] = ceil_row
        return rows

    # -- image --------------------------------------------------------------

    def frame(self, game):
        """Construit l'image complete et renvoie la liste des lignes."""
        w, h = self.w, self.h
        px, py = game.px, game.py
        dx, dy = game.dir_x, game.dir_y
        plane_x, plane_y = -dy * FOV, dx * FOV
        grid, texmap = game.grid, game.texmap
        flicker = game.flicker
        max_line = 4 * h
        # Le fond est calcule par lignes puis transpose d'un coup : zip()
        # travaille en C, c'est bien plus rapide qu'une boucle Python.
        background = [list(column) for column in zip(*self.background(game))]

        columns = []
        zbuffer = [0.0] * w
        for x in range(w):
            camera = 2.0 * x / w - 1.0
            ray_x = dx + plane_x * camera
            ray_y = dy + plane_y * camera

            map_x, map_y = int(px), int(py)
            delta_x = abs(1.0 / ray_x) if ray_x else 1e30
            delta_y = abs(1.0 / ray_y) if ray_y else 1e30
            if ray_x < 0:
                step_x, side_x = -1, (px - map_x) * delta_x
            else:
                step_x, side_x = 1, (map_x + 1.0 - px) * delta_x
            if ray_y < 0:
                step_y, side_y = -1, (py - map_y) * delta_y
            else:
                step_y, side_y = 1, (map_y + 1.0 - py) * delta_y

            side = 0
            for _ in range(128):  # DDA : on avance de case en case
                if side_x < side_y:
                    side_x += delta_x
                    map_x += step_x
                    side = 0
                else:
                    side_y += delta_y
                    map_y += step_y
                    side = 1
                if grid[map_y][map_x]:
                    break

            if side == 0:
                perp = side_x - delta_x
            else:
                perp = side_y - delta_y
            zbuffer[x] = perp
            if perp < 0.2:
                perp = 0.2

            line_h = int(h / perp)
            if line_h < 1:
                line_h = 1
            elif line_h > max_line:
                line_h = max_line

            wall = py + perp * ray_y if side == 0 else px + perp * ray_x
            wall -= math.floor(wall)
            tx = int(wall * TEX)
            if (side == 0 and ray_x > 0) or (side == 1 and ray_y < 0):
                tx = TEX - 1 - tx

            light = flicker * (1.0 - perp / FOG)
            if side:
                light *= 0.68
            level = int((0.05 + 0.95 * (light if light > 0.0 else 0.0)) * (SHADES - 1))
            if level < 0:
                level = 0
            elif level >= SHADES:
                level = SHADES - 1

            texture = self.wall_column(texmap[map_y][map_x], tx, level)
            start, end, ymap = self.span(line_h)
            plane = background[x]
            plane[start:end] = [texture[t] for t in ymap]
            columns.append(plane)

        self._draw_sprites(game, columns, zbuffer, plane_x, plane_y)
        self._draw_torch(game, columns)
        self._draw_crosshair(game, columns)

        rows = [list(row) for row in zip(*columns)]
        self._draw_minimap(game, rows)
        return rows

    def _draw_sprites(self, game, columns, zbuffer, plane_x, plane_y):
        """Projette les sprites, du plus lointain au plus proche."""
        w, h = self.w, self.h
        px, py = game.px, game.py
        dx, dy = game.dir_x, game.dir_y
        det = plane_x * dy - dx * plane_y
        if not det:
            return
        inv = 1.0 / det

        visibles = [(sx, sy, kind) for sx, sy, kind in game.sprite_list()]
        visibles.sort(key=lambda s: -((s[0] - px) ** 2 + (s[1] - py) ** 2))

        for sx, sy, kind in visibles:
            rel_x, rel_y = sx - px, sy - py
            trans_x = inv * (dy * rel_x - dx * rel_y)
            depth = inv * (-plane_y * rel_x + plane_x * rel_y)
            if depth < 0.25:
                continue

            screen_x = int(w * 0.5 * (1.0 + trans_x / depth))
            size = int(h / depth)
            if size < 2:
                continue
            top = self.h // 2 - size // 2
            left = screen_x - size // 2

            if kind == 1:
                # Le portail est une source de lumiere : il ne subit pas le
                # brouillard, sinon le joueur n'aurait aucun point de repere.
                level = SHADES - 1
            else:
                light = game.flicker * (1.0 - depth / FOG)
                level = int((0.10 + 0.90 * max(0.0, light)) * (SHADES - 1))
                level = max(0, min(SHADES - 1, level))

            y0 = max(0, top)
            y1 = min(h, top + size)
            if y1 <= y0:
                continue
            ratio = SPR / size
            ymap = [min(SPR - 1, int((y - top) * ratio)) for y in range(y0, y1)]

            for stripe in range(max(0, left), min(w, left + size)):
                if depth >= zbuffer[stripe]:
                    continue
                tx = int((stripe - left) * ratio)
                if tx < 0 or tx >= SPR:
                    continue
                source = self.sprite_column(kind, tx, level)
                target = columns[stripe]
                y = y0
                for ty in ymap:
                    pixel = source[ty]
                    if pixel is not None:
                        target[y] = pixel
                    y += 1

    def _draw_torch(self, game, columns):
        """Dessine la torche tenue par le joueur, en bas a droite."""
        w, h = self.w, self.h
        flame = game.flicker
        base_x = w - 22
        if base_x < 0:
            return
        for i in range(18):
            x = base_x + i
            if x >= w:
                break
            column = columns[x]
            centre = abs(i - 8.5)
            # le manche
            for y in range(h - 8, h):
                if centre < 2.0:
                    column[y] = (74, 52, 34)
            # la flamme
            height = int(9 * flame) + 3
            for k in range(height):
                y = h - 8 - k
                if y < 0:
                    break
                spread = 4.2 * (1.0 - k / (height + 1.0))
                if centre < spread:
                    heat = 1.0 - (centre / (spread + 0.01)) * 0.55 - k * 0.04
                    heat = max(0.15, min(1.0, heat)) * flame
                    column[y] = (
                        _clamp(int(255 * heat)),
                        _clamp(int(170 * heat * heat)),
                        _clamp(int(60 * heat * heat * heat)),
                    )

    def _draw_crosshair(self, game, columns):
        """Un petit reticule au centre, rouge quand on vient de tirer."""
        w, h = self.w, self.h
        colour = (255, 90, 80) if game.flash > 0 else (210, 210, 210)
        cx, cy = w // 2, h // 2
        for offset in (-3, -2, 2, 3):
            if 0 <= cx + offset < w:
                columns[cx + offset][cy] = colour
            if 0 <= cy + offset < h:
                columns[cx][cy + offset] = colour

    def _draw_minimap(self, game, rows):
        """Carte du labyrinthe autour du joueur, en haut a droite."""
        span = 21
        half = span // 2
        size = len(game.grid)
        ox = self.w - span - 2
        oy = 1
        if ox < 1:
            return
        cx, cy = int(game.px), int(game.py)
        ennemis = {(int(e.x), int(e.y)) for e in game.enemies}

        for j in range(-1, span + 1):
            for i in range(-1, span + 1):
                ry, rx = oy + j, ox + i
                if not (0 <= ry < self.h and 0 <= rx < self.w):
                    continue
                if i < 0 or j < 0 or i >= span or j >= span:
                    rows[ry][rx] = (70, 74, 90)  # le cadre
                    continue
                mx, my = cx - half + i, cy - half + j
                if not (0 <= mx < size and 0 <= my < size):
                    rows[ry][rx] = (10, 10, 14)
                    continue
                if (mx, my) == (cx, cy):
                    colour = (255, 70, 70)
                elif (mx, my) in ennemis:
                    colour = (120, 255, 236)
                elif (mx, my) == game.exit_cell:
                    colour = (70, 255, 140)
                elif game.grid[my][mx]:
                    colour = (96, 92, 104)
                else:
                    colour = (26, 26, 34)
                rows[ry][rx] = colour

    # -- sortie terminal ----------------------------------------------------

    def encode(self, rows, status: str) -> str:
        """Transforme l'image en sequence ANSI, deux pixels par caractere.

        On n'emet un code couleur que lorsque la couleur change : sur une
        image reelle cela divise la taille de la trame par trois ou quatre.
        """
        out = ["\x1b[H"]
        append = out.append
        width = self.w
        for y in range(0, self.h, 2):
            top = rows[y]
            bottom = rows[y + 1]
            append("\x1b[%d;1H" % (y // 2 + 1))
            last_fg = last_bg = None
            for x in range(width):
                fg = top[x]
                bg = bottom[x]
                if fg != last_fg:
                    append("\x1b[38;2;%d;%d;%dm" % fg)
                    last_fg = fg
                if bg != last_bg:
                    append("\x1b[48;2;%d;%d;%dm" % bg)
                    last_bg = bg
                append("▀")
            append("\x1b[0m")
        append("\x1b[%d;1H\x1b[0m\x1b[K%s" % (self.h // 2 + 1, status))
        return "".join(out)


# --------------------------------------------------------------------------
# Jeu
# --------------------------------------------------------------------------


class Enemy:
    """Un spectre : poursuit le joueur des qu'il le voit, erre sinon."""

    __slots__ = ("x", "y", "wander_x", "wander_y", "timer")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.wander_x = 0.0
        self.wander_y = 0.0
        self.timer = 0.0


class Game:
    """Etat du monde et regles du jeu."""

    def __init__(self, seed: int, enemies: int):
        self.rnd = random.Random(seed)
        self.grid, self.texmap = generate_maze(MAZE, self.rnd)
        self.px, self.py = 1.5, 1.5
        self.dir_x, self.dir_y = 1.0, 0.0
        self.health = 100.0
        self.score = 0
        self.flash = 0.0
        self.flicker = 1.0
        self.last_shot = -10.0
        self.started = time.perf_counter()
        self.outcome = None  # None, "win" ou "dead"

        cells = open_cells(self.grid)
        self.exit_cell = max(cells, key=lambda c: c[0] + c[1])
        loin = [c for c in cells
                if (c[0] - 1) ** 2 + (c[1] - 1) ** 2 > 64]
        self.rnd.shuffle(loin)
        self.enemies = [Enemy(c[0] + 0.5, c[1] + 0.5) for c in loin[:enemies]]
        self.total_enemies = len(self.enemies)

    # -- utilitaires --------------------------------------------------------

    def walkable(self, x: float, y: float, radius: float = 0.28) -> bool:
        """Vrai si un disque de rayon donne tient a cet endroit."""
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                cx, cy = int(x + ox), int(y + oy)
                if not (0 <= cx < MAZE and 0 <= cy < MAZE) or self.grid[cy][cx]:
                    return False
        return True

    def visible(self, x0, y0, x1, y1) -> bool:
        """Ligne de vue : on echantillonne le segment a la recherche d'un mur."""
        dx, dy = x1 - x0, y1 - y0
        distance = math.hypot(dx, dy)
        steps = int(distance / 0.2) + 1
        for i in range(1, steps):
            t = i / steps
            if self.grid[int(y0 + dy * t)][int(x0 + dx * t)]:
                return False
        return True

    def sprite_list(self):
        """Tous les sprites a dessiner : les spectres, puis la sortie."""
        for enemy in self.enemies:
            yield enemy.x, enemy.y, 0
        yield self.exit_cell[0] + 0.5, self.exit_cell[1] + 0.5, 1

    # -- boucle -------------------------------------------------------------

    def update(self, keys: KeyReader, dt: float, now: float) -> None:
        self.flicker = 0.88 + 0.12 * math.sin(now * 11.0) * math.sin(now * 4.3) \
            + 0.04 * self.rnd.random()
        self.flicker = max(0.70, min(1.0, self.flicker))
        self.flash = max(0.0, self.flash - dt)

        self._move(keys, dt)
        if keys.take("space"):
            self._shoot(now)
        self._update_enemies(dt)

        if (int(self.px), int(self.py)) == self.exit_cell:
            self.outcome = "win"
        elif self.health <= 0.0:
            self.outcome = "dead"

    def _move(self, keys: KeyReader, dt: float) -> None:
        # Schema de commandes historique de Doom : les fleches tournent, les
        # touches de gauche avancent et font les pas de cote. Cela evite le
        # conflit AZERTY/QWERTY sur les touches A, Q, W et Z.
        turn = 0.0
        if keys.down("left"):
            turn += TURN_SPEED * dt
        if keys.down("right"):
            turn -= TURN_SPEED * dt
        if turn:
            cos, sin = math.cos(turn), math.sin(turn)
            self.dir_x, self.dir_y = (
                self.dir_x * cos - self.dir_y * sin,
                self.dir_x * sin + self.dir_y * cos,
            )

        forward = 0.0
        if keys.down("w", "z", "up"):
            forward += MOVE_SPEED * dt
        if keys.down("s", "down"):
            forward -= MOVE_SPEED * dt
        strafe = 0.0
        if keys.down("a", "q"):
            strafe -= STRAFE_SPEED * dt
        if keys.down("d"):
            strafe += STRAFE_SPEED * dt

        nx = self.px + self.dir_x * forward - self.dir_y * strafe
        ny = self.py + self.dir_y * forward + self.dir_x * strafe
        # On teste chaque axe separement : on glisse le long des murs au lieu
        # de rester bloque dans les angles.
        if self.walkable(nx, self.py):
            self.px = nx
        if self.walkable(self.px, ny):
            self.py = ny

    def _shoot(self, now: float) -> None:
        if now - self.last_shot < SHOT_COOLDOWN:
            return
        self.last_shot = now
        self.flash = 0.09

        cible, meilleure = None, SHOT_RANGE
        for enemy in self.enemies:
            dx, dy = enemy.x - self.px, enemy.y - self.py
            distance = math.hypot(dx, dy)
            if distance > meilleure or distance < 0.001:
                continue
            if (dx * self.dir_x + dy * self.dir_y) / distance < SHOT_APERTURE:
                continue
            if not self.visible(self.px, self.py, enemy.x, enemy.y):
                continue
            cible, meilleure = enemy, distance
        if cible is not None:
            self.enemies.remove(cible)
            self.score += 100

    def _update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            dx, dy = self.px - enemy.x, self.py - enemy.y
            distance = math.hypot(dx, dy)
            if distance < 0.85:
                self.health -= ENEMY_DAMAGE * dt
                continue
            if distance < 11.0 and self.visible(enemy.x, enemy.y, self.px, self.py):
                vx, vy = dx / distance, dy / distance
            else:
                enemy.timer -= dt
                if enemy.timer <= 0.0:
                    angle = self.rnd.random() * math.tau
                    enemy.wander_x = math.cos(angle)
                    enemy.wander_y = math.sin(angle)
                    enemy.timer = 1.2 + self.rnd.random()
                vx, vy = enemy.wander_x, enemy.wander_y
            step = ENEMY_SPEED * dt
            if self.walkable(enemy.x + vx * step, enemy.y, 0.22):
                enemy.x += vx * step
            else:
                enemy.timer = 0.0
            if self.walkable(enemy.x, enemy.y + vy * step, 0.22):
                enemy.y += vy * step
            else:
                enemy.timer = 0.0

    def status(self, fps: float) -> str:
        """Ligne d'etat affichee sous l'image."""
        pv = max(0, int(self.health))
        barre = "█" * (pv // 10) + "░" * (10 - pv // 10)
        ecoule = time.perf_counter() - self.started
        return (
            "\x1b[38;2;255;90;80mPV\x1b[0m %s %3d   "
            "\x1b[38;2;120;255;236mSPECTRES\x1b[0m %d/%d   "
            "\x1b[38;2;255;210;90mSCORE\x1b[0m %4d   "
            "TEMPS %02d:%02d   FPS %4.1f   "
            "\x1b[2m[ZQSD/WASD] bouger  [fleches] tourner  "
            "[ESPACE] tirer  [ECHAP] quitter\x1b[0m"
            % (barre, pv, self.total_enemies - len(self.enemies),
               self.total_enemies, self.score,
               int(ecoule) // 60, int(ecoule) % 60, fps)
        )


# --------------------------------------------------------------------------
# Terminal
# --------------------------------------------------------------------------


def enable_ansi() -> None:
    """Active les sequences ANSI sur les consoles Windows et force l'UTF-8."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if os.name != "nt":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def terminal_size(requested):
    """Choisit la resolution de rendu : demandee, ou deduite du terminal."""
    if requested:
        w, h = (int(v) for v in requested.lower().split("x"))
        return max(40, w), max(20, h - h % 2)
    cols, lines = shutil.get_terminal_size((100, 30))
    w = max(40, min(cols - 1, 150))
    h = max(20, min((lines - 2) * 2, 96))
    return w, h - h % 2


def title_screen(keys) -> bool:
    """Ecran d'accueil. Renvoie False si le joueur quitte tout de suite."""
    or_ = "\x1b[38;2;255;170;60m"
    art = [
        "",
        "   " + or_ + "╔" + "═" * 52 + "╗\x1b[0m",
        "   " + or_ + "║\x1b[0m  \x1b[1mC R Y P T E\x1b[0m"
        + " " * 39 + or_ + "║\x1b[0m",
        "   " + or_ + "║\x1b[0m  \x1b[2mmoteur 3D temps reel, en Python pur"
        "\x1b[0m" + " " * 15 + or_ + "║\x1b[0m",
        "   " + or_ + "╚" + "═" * 52 + "╝\x1b[0m",
        "",
        "   \x1b[2mLancer de rayons, textures et sprites generes par le code.\x1b[0m",
        "   \x1b[2mAucune dependance : uniquement la bibliotheque standard.\x1b[0m",
        "",
        "   \x1b[38;2;120;255;236mBut\x1b[0m       trouver le portail vert "
        "au fond de la crypte.",
        "   \x1b[38;2;255;90;80mDanger\x1b[0m    les spectres vous suivent "
        "des qu'ils vous voient.",
        "",
        "   \x1b[1mZ/W\x1b[0m et \x1b[1mS\x1b[0m   avancer, reculer      "
        "\x1b[1mfleches\x1b[0m  tourner",
        "   \x1b[1mQ/A\x1b[0m et \x1b[1mD\x1b[0m   pas de cote          "
        "\x1b[1mESPACE\x1b[0m   tirer",
        "   \x1b[1mECHAP\x1b[0m      quitter",
        "",
        "   \x1b[38;2;255;210;90mAppuyez sur ENTREE pour entrer.\x1b[0m",
        "",
    ]
    sys.stdout.write("\x1b[2J\x1b[H" + "\n".join(art))
    sys.stdout.flush()
    while True:
        keys.poll(time.perf_counter())
        if keys.take("enter") or keys.take("space"):
            keys.clear()
            return True
        if keys.take("esc") or keys.take("x"):
            return False
        time.sleep(0.02)


def end_screen(game) -> None:
    ecoule = time.perf_counter() - game.started
    if game.outcome == "win":
        titre = "\x1b[38;2;70;255;140mVOUS AVEZ TROUVE LA SORTIE\x1b[0m"
    else:
        titre = "\x1b[38;2;255;70;70mLES SPECTRES VOUS ONT EU\x1b[0m"
    sys.stdout.write(
        "\x1b[2J\x1b[H\n  %s\n\n  Score  %d\n  Spectres elimines  %d/%d\n"
        "  Temps  %02d:%02d\n\n"
        % (titre, game.score, game.total_enemies - len(game.enemies),
           game.total_enemies, int(ecoule) // 60, int(ecoule) % 60)
    )


def play(renderer, seed, enemies) -> None:
    """Boucle principale du jeu."""
    with KeyReader() as keys:
        if not title_screen(keys):
            return
        game = Game(seed, enemies)
        sys.stdout.write("\x1b[2J" + UP)
        previous = time.perf_counter()
        fps = 0.0
        while game.outcome is None:
            now = time.perf_counter()
            dt = min(0.05, now - previous)
            previous = now

            keys.poll(now)
            if keys.take("esc") or keys.take("x"):
                break
            game.update(keys, dt, now)

            rows = renderer.frame(game)
            fps = fps * 0.9 + (1.0 / max(dt, 1e-6)) * 0.1
            sys.stdout.write(renderer.encode(rows, game.status(fps)))
            sys.stdout.flush()

            reste = (1.0 / TARGET_FPS) - (time.perf_counter() - now)
            if reste > 0:
                time.sleep(reste)
        sys.stdout.write(DOWN)
        if game.outcome:
            end_screen(game)


def write_png(path: str, rows, scale: int = 4) -> None:
    """Ecrit l'image en PNG sans aucune dependance.

    Un PNG est une suite de blocs longueur/type/donnees/CRC. Les pixels sont
    stockes ligne par ligne, chacune precedee de son octet de filtre (0 = pas
    de filtre), le tout compresse avec zlib. struct et zlib suffisent donc.
    """
    import struct
    import zlib

    height = len(rows)
    width = len(rows[0])
    brut = bytearray()
    for row in rows:
        ligne = bytearray()
        for pixel in row:
            ligne += bytes(pixel) * scale
        for _ in range(scale):
            brut.append(0)  # octet de filtre
            brut += ligne

    def bloc(tag: bytes, data: bytes) -> bytes:
        corps = tag + data
        return (struct.pack(">I", len(data)) + corps
                + struct.pack(">I", zlib.crc32(corps)))

    entete = struct.pack(">IIBBBBB", width * scale, height * scale, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + bloc(b"IHDR", entete)
           + bloc(b"IDAT", zlib.compress(bytes(brut), 9))
           + bloc(b"IEND", b""))
    with open(path, "wb") as sortie:
        sortie.write(png)


def capture(renderer, seed, enemies, path) -> None:
    """Ecrit une image de presentation du moteur, sans lancer de partie.

    La camera est posee dans le plus long couloir droit du labyrinthe, avec
    un spectre a trois cases et le portail au fond : c'est la vue qui montre
    le mieux le lancer de rayons, les textures et les sprites.
    """
    game = Game(seed, max(1, enemies))
    game.flicker = 1.0
    meilleur = None
    for cx, cy in open_cells(game.grid):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            longueur = 1
            while game.grid[cy + dy * longueur][cx + dx * longueur] == 0:
                longueur += 1
            if meilleur is None or longueur > meilleur[0]:
                meilleur = (longueur, cx, cy, dx, dy)
    longueur, cx, cy, dx, dy = meilleur
    game.px, game.py = cx + 0.5, cy + 0.5
    game.dir_x, game.dir_y = float(dx), float(dy)
    game.enemies = [Enemy(cx + 0.5 + dx * 3, cy + 0.5 + dy * 3)]
    game.exit_cell = (cx + dx * min(9, longueur - 1),
                      cy + dy * min(9, longueur - 1))

    write_png(path, renderer.frame(game))
    print("image ecrite : %s (%d x %d pixels, couloir de %d cases)"
          % (path, renderer.w, renderer.h, longueur))


def benchmark(renderer, seed, enemies, frames) -> None:
    """Rend N images sans rien afficher, pour mesurer les performances."""
    game = Game(seed, enemies)
    keys = KeyReader()
    start = time.perf_counter()
    octets = 0
    for i in range(frames):
        game.dir_x = math.cos(i * 0.02)
        game.dir_y = math.sin(i * 0.02)
        game.update(keys, 1.0 / 60.0, start + i / 60.0)
        octets += len(renderer.encode(renderer.frame(game), game.status(60.0)))
    ecoule = time.perf_counter() - start
    print("resolution      %d x %d pixels (%d x %d cellules)"
          % (renderer.w, renderer.h, renderer.w, renderer.h // 2))
    print("images rendues  %d en %.2f s" % (frames, ecoule))
    print("cadence         %.1f images/seconde" % (frames / ecoule))
    print("trame moyenne   %.1f Ko" % (octets / frames / 1024))
    print("caches          %d colonnes de mur, %d de sprite, %d hauteurs"
          % (len(renderer._wall_cache), len(renderer._sprite_cache),
             len(renderer._span_cache)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="CRYPTE : moteur 3D temps reel dans le terminal, "
                    "en Python pur.")
    parser.add_argument("--size", help="resolution forcee, par exemple 120x72")
    parser.add_argument("--seed", type=int, default=7, help="graine du labyrinthe")
    parser.add_argument("--enemies", type=int, default=ENEMIES,
                        help="nombre de spectres")
    parser.add_argument("--bench", type=int, metavar="N",
                        help="rend N images sans affichage et mesure les FPS")
    parser.add_argument("--capture", metavar="FICHIER.png",
                        help="ecrit une image de presentation et quitte")
    args = parser.parse_args(argv)

    enable_ansi()
    width, height = terminal_size(args.size)
    renderer = Renderer(width, height)

    if args.bench:
        benchmark(renderer, args.seed, args.enemies, args.bench)
        return 0
    if args.capture:
        capture(renderer, args.seed, args.enemies, args.capture)
        return 0

    try:
        play(renderer, args.seed, args.enemies)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(DOWN + "\x1b[0m\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
