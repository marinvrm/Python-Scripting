from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True)
    nickname = Column(String)
    url = Column(String, nullable=True)

    # Exercice : un utilisateur a plusieurs posts. Supprimer l'utilisateur
    # supprime ses posts (un post ne peut pas exister sans auteur).
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    # nullable=False : un post appartient a exactement un utilisateur.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    author = relationship("User", back_populates="posts")
