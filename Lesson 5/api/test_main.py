"""Tests de l'API : python -m pytest, depuis le dossier api/."""


# ---------------------------------------------------------------- premiers pas

def test_home(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"message": "Hello World"}


def test_item_sans_type_renvoie_une_chaine(client):
    assert client.get("/items/42").json() == {"item_id": "42"}


def test_item_type_int(client):
    assert client.get("/items_type/42").json() == {"item_id": 42}


def test_item_type_refuse_une_chaine(client):
    r = client.get("/items_type/abc")
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "int_parsing"


def test_documentation_generee(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/adduser", "/users", "/addpost", "/posts"} <= set(paths)


# ---------------------------------------------------------------- utilisateurs

def test_add_user(client):
    r = client.post("/adduser", json={"name": "bob", "email": "bob@example.com", "nickname": "b"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["url"] == "http://testserver/user/bob"


def test_add_user_champ_manquant(client):
    r = client.post("/adduser", json={"name": "bob"})
    assert r.status_code == 422


def test_add_user_email_en_double(client, alice):
    r = client.post("/adduser", json={"name": "alice2", "email": "alice@example.com", "nickname": "x"})
    assert r.status_code == 409


def test_get_users(client, alice):
    users = client.get("/users").json()
    assert len(users) == 1
    assert users[0]["id"] == alice["id"]
    assert users[0]["name"] == "alice"


def test_get_user_par_nom(client, alice):
    r = client.get("/user/alice")
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"
    assert r.json()["posts"] == []


def test_get_user_inconnu(client):
    assert client.get("/user/personne").status_code == 404


def test_update_user(client, alice):
    r = client.put(f"/user/{alice['id']}", json={
        "name": "alicia", "email": "alicia@example.com", "nickname": "ali",
    })
    assert r.status_code == 200
    assert r.json()["name"] == "alicia"
    assert r.json()["url"] == "http://testserver/user/alicia"
    assert client.get("/user/alicia").status_code == 200


def test_update_user_inconnu(client):
    r = client.put("/user/99", json={"name": "x", "email": "x@example.com", "nickname": "x"})
    assert r.status_code == 404


def test_delete_user(client, alice):
    r = client.delete(f"/user/{alice['id']}")
    assert r.status_code == 200
    assert client.get("/users").json() == []


def test_delete_user_inconnu(client):
    assert client.delete("/user/99").status_code == 404


def test_delete_user_id_non_entier(client):
    assert client.delete("/user/abc").status_code == 422


# ---------------------------------------------------------------- posts

def make_post(client, user_id, title="Premier post", content="Bonjour"):
    return client.post("/addpost", json={"title": title, "content": content, "user_id": user_id})


def test_add_post(client, alice):
    r = make_post(client, alice["id"])
    assert r.status_code == 200
    assert r.json() == {"id": 1, "title": "Premier post", "content": "Bonjour", "user_id": alice["id"]}


def test_add_post_auteur_inconnu(client):
    assert make_post(client, 99).status_code == 404


def test_get_posts(client, alice):
    make_post(client, alice["id"], "A")
    make_post(client, alice["id"], "B")
    titles = [p["title"] for p in client.get("/posts").json()]
    assert titles == ["A", "B"]


def test_get_post(client, alice):
    post = make_post(client, alice["id"]).json()
    assert client.get(f"/post/{post['id']}").json() == post


def test_get_post_inconnu(client):
    assert client.get("/post/99").status_code == 404


def test_un_utilisateur_a_plusieurs_posts(client, alice):
    bob = client.post("/adduser", json={"name": "bob", "email": "bob@example.com", "nickname": "b"}).json()
    make_post(client, alice["id"], "A1")
    make_post(client, bob["id"], "B1")
    make_post(client, alice["id"], "A2")

    alice_posts = client.get(f"/user/{alice['id']}/posts").json()
    assert [p["title"] for p in alice_posts] == ["A1", "A2"]
    assert [p["title"] for p in client.get("/user/alice").json()["posts"]] == ["A1", "A2"]


def test_posts_d_un_utilisateur_inconnu(client):
    assert client.get("/user/99/posts").status_code == 404


def test_update_post(client, alice):
    post = make_post(client, alice["id"]).json()
    r = client.put(f"/post/{post['id']}", json={"title": "Modifié", "content": "Nouveau texte"})
    assert r.status_code == 200
    assert r.json()["title"] == "Modifié"
    assert r.json()["user_id"] == alice["id"]


def test_update_post_inconnu(client):
    assert client.put("/post/99", json={"title": "x", "content": "y"}).status_code == 404


def test_delete_post(client, alice):
    post = make_post(client, alice["id"]).json()
    assert client.delete(f"/post/{post['id']}").status_code == 200
    assert client.get("/posts").json() == []


def test_delete_post_inconnu(client):
    assert client.delete("/post/99").status_code == 404


def test_supprimer_un_utilisateur_supprime_ses_posts(client, alice):
    make_post(client, alice["id"])
    client.delete(f"/user/{alice['id']}")
    assert client.get("/posts").json() == []
