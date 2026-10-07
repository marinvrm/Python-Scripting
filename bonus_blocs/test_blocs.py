"""Tests des regles de BLOCS, sans fenetre : python test_blocs.py"""

import unittest

from blocs import (HEIGHT, HIDDEN, LOCK_DELAY, MAX_RESETS, SHAPES, WIDTH,
                   Game, gravity_interval)


def game_with(kind, **kwargs):
    g = Game(seed=1, **kwargs)
    g.spawn(kind)
    return g


class TestTirage(unittest.TestCase):
    def test_sac_de_sept(self):
        g = Game(seed=3)
        g.bag = []  # la partie a deja pioche 6 pieces a sa creation
        drawn = [g._next_kind() for _ in range(70)]
        for i in range(0, 70, 7):
            self.assertEqual(sorted(drawn[i:i + 7]), sorted(SHAPES))

    def test_meme_graine_meme_partie(self):
        self.assertEqual(Game(seed=7).queue, Game(seed=7).queue)

    def test_file_de_cinq(self):
        g = Game(seed=1)
        g.hard_drop()
        self.assertEqual(len(g.queue), 5)


class TestMouvements(unittest.TestCase):
    def test_apparition_visible(self):
        for kind in SHAPES:
            g = game_with(kind)
            self.assertTrue(all(y >= HIDDEN for _, y in g.cells()), kind)

    def test_mur_gauche(self):
        g = game_with("T")
        while g.move(-1):
            pass
        self.assertEqual(min(x for x, _ in g.cells()), 0)
        self.assertFalse(g.move(-1))

    def test_mur_droit(self):
        g = game_with("I")
        while g.move(1):
            pass
        self.assertEqual(max(x for x, _ in g.cells()), WIDTH - 1)

    def test_quatre_rotations_reviennent_au_depart(self):
        for kind in SHAPES:
            g = game_with(kind)
            g.step_down()
            g.step_down()
            before = sorted(g.cells())
            for _ in range(4):
                self.assertTrue(g.rotate(1), kind)
            self.assertEqual(sorted(g.cells()), before, kind)

    def test_rotation_contre_le_mur_grace_aux_kicks(self):
        g = game_with("I")
        g.rotate(1)  # verticale
        while g.move(1):
            pass
        self.assertTrue(g.rotate(1))  # redevient horizontale malgre le mur
        self.assertTrue(all(0 <= x < WIDTH for x, _ in g.cells()))

    def test_fantome_au_fond(self):
        g = game_with("O")
        self.assertEqual(max(y for _, y in g.cells(y=g.ghost_y())), HEIGHT - 1)


class TestChute(unittest.TestCase):
    def test_gravite_accelere(self):
        self.assertAlmostEqual(gravity_interval(1), 1.0)
        for lvl in range(1, 20):
            self.assertGreater(gravity_interval(lvl), gravity_interval(lvl + 1))

    def test_gravite_fait_descendre(self):
        g = game_with("T")
        y = g.y
        g.tick(1.01)
        self.assertEqual(g.y, y + 1)

    def test_descente_rapide_rapporte_des_points(self):
        g = game_with("T")
        g.tick(0.2, soft=True)
        self.assertGreater(g.score, 0)

    def test_lacher_rapporte_deux_points_par_ligne(self):
        g = game_with("O")
        rows = g.hard_drop()
        self.assertEqual(g.score, 2 * rows)
        self.assertEqual(g.board[HEIGHT - 1][4], "O")

    def test_verrouillage_apres_delai(self):
        g = game_with("O")
        while g.step_down():
            pass
        g.tick(LOCK_DELAY * 0.8)
        self.assertEqual(g.kind, "O")
        self.assertIsNone(g.board[HEIGHT - 1][4])
        g.tick(LOCK_DELAY * 0.3)
        self.assertEqual(g.board[HEIGHT - 1][4], "O")

    def test_bouger_au_sol_relance_le_delai_mais_pas_a_l_infini(self):
        g = game_with("T")
        while g.step_down():
            pass
        for i in range(MAX_RESETS + 5):
            g.tick(LOCK_DELAY * 0.6)
            if g.board[HEIGHT - 1][3] or g.board[HEIGHT - 1][4]:
                break
            g.move(1 if i % 2 == 0 else -1)
        self.assertLessEqual(i, MAX_RESETS + 1)
        self.assertTrue(any(g.board[HEIGHT - 1]))


class TestLignes(unittest.TestCase):
    def fill_row(self, g, row, holes):
        for x in range(WIDTH):
            if x not in holes:
                g.board[row][x] = "J"

    def test_une_ligne(self):
        g = game_with("I")
        self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
        g.board[HEIGHT - 2][0] = "L"
        g.hard_drop()
        self.assertEqual(g.lines, 1)
        self.assertEqual(g.board[HEIGHT - 1][0], "L")  # la ligne du dessus a glisse
        self.assertEqual(g.score, 100 + 2 * 19)

    def test_tetris_quatre_lignes(self):
        g = game_with("I")
        g.rotate(1)
        for row in range(HEIGHT - 4, HEIGHT):
            self.fill_row(g, row, holes={g.cells()[0][0]})
        g.hard_drop()
        self.assertEqual(g.lines, 4)
        self.assertGreaterEqual(g.score, 800)
        self.assertTrue(all(c is None for row in g.board for c in row))

    def test_niveau_toutes_les_dix_lignes(self):
        g = Game(seed=1, level=3)
        for _ in range(10):
            g.spawn("I")
            self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
            g.hard_drop()
        self.assertEqual(g.lines, 10)
        self.assertEqual(g.level, 4)


def clears(g):
    return [e for e in g.events if e["type"] == "clear"]


class TestBonus(unittest.TestCase):
    def fill_row(self, g, row, holes):
        for x in range(WIDTH):
            if x not in holes:
                g.board[row][x] = "J"

    def t_slot(self, rotated):
        """T pointe vers le bas dans un trou, sous un surplomb en (3, 19)."""
        g = game_with("T")
        self.fill_row(g, HEIGHT - 1, holes={4})
        self.fill_row(g, HEIGHT - 2, holes={3, 4, 5})
        g.board[HEIGHT - 3][3] = "L"
        g.x, g.y, g.rot = 3, HEIGHT - 3, 2
        g.last_rotate = rotated
        g.events.clear()
        g.hard_drop()
        return g

    def test_t_spin_double(self):
        g = self.t_slot(rotated=True)
        (ev,) = clears(g)
        self.assertTrue(ev["tspin"])
        self.assertEqual(ev["count"], 2)
        self.assertEqual(g.score, 1200)

    def test_sans_rotation_ce_n_est_pas_un_t_spin(self):
        g = self.t_slot(rotated=False)
        (ev,) = clears(g)
        self.assertFalse(ev["tspin"])
        self.assertEqual(g.score, 300)

    def test_combo(self):
        g = Game(seed=1)
        for expected in (0, 1, 2):
            g.spawn("I")
            self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
            g.board[HEIGHT - 2][0] = "L"  # evite le bonus plateau vide
            g.events.clear()
            g.hard_drop()
            self.assertEqual(clears(g)[0]["combo"], expected)
        self.assertEqual(g.combo, 2)
        g.hard_drop()  # une piece sans ligne casse le combo
        self.assertEqual(g.combo, -1)

    def test_back_to_back(self):
        g = Game(seed=1)
        flags = []
        for _ in range(2):
            g.spawn("I")
            g.rotate(1)
            col = g.cells()[0][0]
            for row in range(HEIGHT - 4, HEIGHT):
                self.fill_row(g, row, holes={col})
            g.events.clear()
            g.hard_drop()
            flags.append(clears(g)[0]["b2b"])
        self.assertEqual(flags, [False, True])

    def test_plateau_vide(self):
        g = game_with("I")
        self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
        g.events.clear()
        g.hard_drop()
        ev = clears(g)[0]
        self.assertTrue(ev["perfect"])
        self.assertEqual(g.score, 100 + 800 + 2 * 19)

    def test_evenement_decrit_la_chute_des_lignes(self):
        g = game_with("I")
        self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
        g.board[HEIGHT - 2][0] = "L"
        g.events.clear()
        g.hard_drop()
        ev = clears(g)[0]
        self.assertEqual(ev["rows"], [HEIGHT - 1])
        self.assertEqual(ev["shift"][HEIGHT - 1], 1)  # la ligne du dessus descend de 1
        self.assertEqual(ev["before"][HEIGHT - 2][0], "L")
        types = [e["type"] for e in g.events]
        self.assertEqual(types[:3], ["harddrop", "lock", "clear"])

    def test_evenement_de_niveau(self):
        g = Game(seed=1)
        for _ in range(10):
            g.spawn("I")
            self.fill_row(g, HEIGHT - 1, holes={3, 4, 5, 6})
            g.hard_drop()
        self.assertIn({"type": "level", "level": 2}, g.events)


class TestReserve(unittest.TestCase):
    def test_premiere_reserve(self):
        g = game_with("T")
        nxt = g.queue[0]
        self.assertTrue(g.hold())
        self.assertEqual(g.hold_kind, "T")
        self.assertEqual(g.kind, nxt)

    def test_une_seule_fois_par_piece(self):
        g = game_with("T")
        g.hold()
        self.assertFalse(g.hold())
        g.hard_drop()
        self.assertTrue(g.hold())

    def test_echange(self):
        g = game_with("T")
        g.hold()
        g.hard_drop()
        current = g.kind
        g.hold()
        self.assertEqual(g.kind, "T")
        self.assertEqual(g.hold_kind, current)


class TestFinDePartie(unittest.TestCase):
    def test_plateau_plein(self):
        g = Game(seed=1)
        for row in range(HIDDEN, HEIGHT):
            for x in range(WIDTH - 1):
                g.board[row][x] = "Z"
        g.hard_drop()
        self.assertTrue(g.over)
        self.assertFalse(g.move(1))
        self.assertFalse(g.hold())


if __name__ == "__main__":
    unittest.main(verbosity=2)
