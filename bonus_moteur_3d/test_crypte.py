"""Tests du moteur CRYPTE, avec unittest (bibliotheque standard).

Le rendu et la logique sont testables sans terminal : le moteur rend dans
une liste de pixels, et la boucle de jeu ne lit le clavier qu'a travers un
objet que l'on peut remplacer.

    python test_crypte.py
"""

from __future__ import annotations

import math
import unittest
from collections import deque

import crypte


class FauxClavier:
    """Clavier simule : on decide directement des touches enfoncees."""

    def __init__(self, held=(), events=()):
        self.held = set(held)
        self.events = deque(events)

    def down(self, *keys):
        return any(k in self.held for k in keys)

    def take(self, key):
        if key in self.events:
            self.events = deque(k for k in self.events if k != key)
            return True
        return False


def partie(enemies=0, seed=7):
    """Une partie sans spectre, sauf demande explicite."""
    return crypte.Game(seed, enemies)


class TestLabyrinthe(unittest.TestCase):

    def test_bordures_fermees(self):
        grid, _ = crypte.generate_maze(crypte.MAZE, crypte.random.Random(1))
        taille = len(grid)
        for i in range(taille):
            self.assertEqual(grid[0][i], 1)
            self.assertEqual(grid[taille - 1][i], 1)
            self.assertEqual(grid[i][0], 1)
            self.assertEqual(grid[i][taille - 1], 1)

    def test_toutes_les_cases_sont_accessibles(self):
        """Aucune salle isolee : sinon la sortie pourrait etre inatteignable."""
        for seed in range(6):
            grid, _ = crypte.generate_maze(crypte.MAZE, crypte.random.Random(seed))
            ouvertes = set(crypte.open_cells(grid))
            vues = {(1, 1)}
            file = deque([(1, 1)])
            while file:
                x, y = file.popleft()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    voisin = (x + dx, y + dy)
                    if voisin in ouvertes and voisin not in vues:
                        vues.add(voisin)
                        file.append(voisin)
            self.assertEqual(vues, ouvertes, "graine %d : labyrinthe coupe" % seed)

    def test_depart_et_sortie_praticables(self):
        jeu = partie()
        self.assertTrue(jeu.walkable(jeu.px, jeu.py))
        ex, ey = jeu.exit_cell
        self.assertEqual(jeu.grid[ey][ex], 0)


class TestCollisions(unittest.TestCase):

    def test_un_mur_bloque(self):
        jeu = partie()
        self.assertFalse(jeu.walkable(0.5, 0.5))  # le mur du bord

    def test_on_ne_traverse_pas_les_murs(self):
        jeu = partie()
        jeu.px, jeu.py = 1.5, 1.5
        jeu.dir_x, jeu.dir_y = -1.0, 0.0  # face au mur de gauche
        for _ in range(60):
            jeu._move(FauxClavier(held={"w"}), 0.05)
        self.assertTrue(jeu.walkable(jeu.px, jeu.py))
        self.assertGreater(jeu.px, 1.0)

    def test_on_glisse_le_long_des_murs(self):
        """Un deplacement en diagonale contre un mur ne doit pas tout bloquer."""
        jeu = partie()
        jeu.px, jeu.py = 1.5, 1.5
        jeu.dir_x, jeu.dir_y = math.cos(0.6), math.sin(0.6)
        avant = (jeu.px, jeu.py)
        for _ in range(10):
            jeu._move(FauxClavier(held={"w"}), 0.05)
        self.assertNotEqual((jeu.px, jeu.py), avant)


class TestCombat(unittest.TestCase):

    def _couloir(self):
        """Renvoie une partie placee dans un long couloir droit."""
        jeu = partie()
        meilleur = None
        for (cx, cy) in crypte.open_cells(jeu.grid):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = 1
                while jeu.grid[cy + dy * n][cx + dx * n] == 0:
                    n += 1
                if meilleur is None or n > meilleur[0]:
                    meilleur = (n, cx, cy, dx, dy)
        _, cx, cy, dx, dy = meilleur
        jeu.px, jeu.py = cx + 0.5, cy + 0.5
        jeu.dir_x, jeu.dir_y = float(dx), float(dy)
        return jeu, dx, dy

    def test_le_tir_touche_une_cible_dans_l_axe(self):
        jeu, dx, dy = self._couloir()
        jeu.enemies = [crypte.Enemy(jeu.px + dx * 3, jeu.py + dy * 3)]
        jeu._shoot(now=100.0)
        self.assertEqual(jeu.enemies, [])
        self.assertEqual(jeu.score, 100)

    def test_le_tir_rate_une_cible_hors_de_l_axe(self):
        jeu, dx, dy = self._couloir()
        # a 90 degres de la direction visee
        jeu.enemies = [crypte.Enemy(jeu.px + dy * 3, jeu.py + dx * 3)]
        jeu._shoot(now=100.0)
        self.assertEqual(len(jeu.enemies), 1)

    def test_le_tir_ne_traverse_pas_les_murs(self):
        jeu, dx, dy = self._couloir()
        # On mure le couloir juste devant le joueur.
        jeu.grid[int(jeu.py + dy * 2)][int(jeu.px + dx * 2)] = 1
        jeu.enemies = [crypte.Enemy(jeu.px + dx * 4, jeu.py + dy * 4)]
        jeu._shoot(now=100.0)
        self.assertEqual(len(jeu.enemies), 1)

    def test_temps_de_recharge(self):
        jeu, dx, dy = self._couloir()
        jeu.enemies = [crypte.Enemy(jeu.px + dx * 3, jeu.py + dy * 3),
                       crypte.Enemy(jeu.px + dx * 5, jeu.py + dy * 5)]
        jeu._shoot(now=100.0)
        jeu._shoot(now=100.0 + crypte.SHOT_COOLDOWN / 2)
        self.assertEqual(len(jeu.enemies), 1, "le second tir aurait du etre refuse")

    def test_un_spectre_au_contact_blesse(self):
        jeu = partie()
        jeu.enemies = [crypte.Enemy(jeu.px + 0.2, jeu.py)]
        jeu._update_enemies(1.0)
        self.assertAlmostEqual(jeu.health, 100.0 - crypte.ENEMY_DAMAGE, places=5)

    def test_un_spectre_qui_voit_le_joueur_s_approche(self):
        jeu, dx, dy = self._couloir()
        spectre = crypte.Enemy(jeu.px + dx * 4, jeu.py + dy * 4)
        jeu.enemies = [spectre]
        avant = math.hypot(spectre.x - jeu.px, spectre.y - jeu.py)
        for _ in range(20):
            jeu._update_enemies(0.05)
        apres = math.hypot(spectre.x - jeu.px, spectre.y - jeu.py)
        self.assertLess(apres, avant)


class TestFinDePartie(unittest.TestCase):

    def test_victoire_sur_la_case_de_sortie(self):
        jeu = partie()
        jeu.px, jeu.py = jeu.exit_cell[0] + 0.5, jeu.exit_cell[1] + 0.5
        jeu.update(FauxClavier(), 0.016, 1.0)
        self.assertEqual(jeu.outcome, "win")

    def test_defaite_a_zero_point_de_vie(self):
        jeu = partie()
        jeu.health = 0.0
        jeu.update(FauxClavier(), 0.016, 1.0)
        self.assertEqual(jeu.outcome, "dead")

    def test_partie_en_cours_par_defaut(self):
        self.assertIsNone(partie().outcome)


class TestRendu(unittest.TestCase):

    def setUp(self):
        self.renderer = crypte.Renderer(60, 40)
        self.jeu = partie(enemies=3)

    def test_dimensions_de_l_image(self):
        rows = self.renderer.frame(self.jeu)
        self.assertEqual(len(rows), 40)
        for row in rows:
            self.assertEqual(len(row), 60)

    def test_tous_les_pixels_sont_valides(self):
        for row in self.renderer.frame(self.jeu):
            for pixel in row:
                self.assertEqual(len(pixel), 3)
                for composante in pixel:
                    self.assertTrue(0 <= composante <= 255, pixel)

    def test_le_fond_couvre_toute_l_image(self):
        rows = self.renderer.background(self.jeu)
        self.assertEqual(len(rows), 40)
        self.assertTrue(all(len(row) == 60 for row in rows))

    def test_hauteur_impaire_ramenee_au_pair(self):
        """Un pixel du haut et un du bas par cellule : il en faut un nombre pair."""
        self.assertEqual(crypte.Renderer(60, 41).h, 40)

    def test_encodage_ansi(self):
        rows = self.renderer.frame(self.jeu)
        trame = self.renderer.encode(rows, "etat")
        self.assertEqual(trame.count("▀"), 60 * 20)
        self.assertIn("\x1b[38;2;", trame)
        self.assertIn("\x1b[48;2;", trame)
        self.assertTrue(trame.endswith("etat"))

    def test_les_murs_proches_sont_plus_clairs_que_les_lointains(self):
        """Verifie que le brouillard de distance agit bien."""
        proche = self.renderer.wall_column(0, 0, crypte.SHADES - 1)
        lointain = self.renderer.wall_column(0, 0, 1)
        self.assertGreater(sum(sum(p) for p in proche),
                           sum(sum(p) for p in lointain))

    def test_les_caches_se_remplissent(self):
        self.renderer.frame(self.jeu)
        self.assertTrue(self.renderer._wall_cache)
        self.assertTrue(self.renderer._plane_cache)
        self.assertTrue(self.renderer._span_cache)

    def test_le_cache_de_hauteurs_reste_borne(self):
        """Sans borne sur la hauteur de colonne, le cache grossirait sans fin."""
        for _ in range(400):
            self.renderer.frame(self.jeu)
            self.jeu.px += 0.001
        self.assertLessEqual(len(self.renderer._span_cache), 4 * self.renderer.h + 2)


class TestTextures(unittest.TestCase):

    def test_quatre_murs_de_bonne_taille(self):
        textures = crypte.build_textures()
        self.assertEqual(len(textures), 4)
        for texture in textures:
            self.assertEqual(len(texture), crypte.TEX)
            self.assertTrue(all(len(col) == crypte.TEX for col in texture))

    def test_sol_et_plafond_sont_plats(self):
        rnd = crypte.random.Random(0)
        for flat in (crypte._flagstone_floor(rnd), crypte._rock_ceiling(rnd)):
            self.assertEqual(len(flat), crypte.TEX * crypte.TEX)

    def test_les_sprites_ont_de_la_transparence(self):
        for sprite in (crypte._ghost_sprite(), crypte._portal_sprite()):
            pixels = [p for col in sprite for p in col]
            self.assertEqual(len(pixels), crypte.SPR * crypte.SPR)
            self.assertIn(None, pixels, "un sprite sans transparence est un carre")


if __name__ == "__main__":
    unittest.main(verbosity=2)
