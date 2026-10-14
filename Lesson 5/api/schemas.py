from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------- utilisateurs

class UserSchema(BaseModel):
    """Donnees envoyees par le client pour creer ou modifier un utilisateur."""

    name: str
    email: str
    nickname: str
    url: Optional[str] = None

    # Pydantic 2 : orm_mode est devenu from_attributes, et la classe Config
    # interne est remplacee par model_config.
    model_config = ConfigDict(from_attributes=True)


class UserOut(UserSchema):
    """Ce que l'API renvoie : les memes champs, plus l'id genere par la base."""

    id: int


# ---------------------------------------------------------------- posts

class PostCreate(BaseModel):
    title: str
    content: str
    user_id: int


class PostUpdate(BaseModel):
    """Modification d'un post : l'auteur ne change pas."""

    title: str
    content: str


class PostOut(BaseModel):
    id: int
    title: str
    content: str
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class UserWithPosts(UserOut):
    posts: list[PostOut] = []
