from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Post, User
from schemas import PostCreate, PostOut, PostUpdate, UserOut, UserSchema, UserWithPosts

# Cree les tables "users" et "posts" si elles n'existent pas encore.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lesson 5 - FastAPI")


def get_db():
    # La session est ouverte avant le try : si SessionLocal() echouait a
    # l'interieur, le finally appellerait close() sur une variable inexistante.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def user_url(request: Request, name: str) -> str:
    return f"{request.base_url}user/{name}"


def commit_or_409(db: Session):
    # email est unique : un doublon leve IntegrityError au commit. Sans ce
    # bloc, le client recevrait une erreur 500 au lieu d'un message clair.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cet email est deja utilise")


# =====================================================================
# Premiers pas
# =====================================================================

@app.get("/")
async def home():
    return {"message": "Hello World"}


@app.get("/items/{item_id}")
async def read_item(item_id):
    return {"item_id": item_id}


@app.get("/items_type/{item_id}")
async def read_item_typed(item_id: int):
    return {"item_id": item_id}


# =====================================================================
# Utilisateurs (cours)
#
# Les routes qui interrogent la base sont des "def" et non des "async def" :
# SQLAlchemy est synchrone, et FastAPI execute les "def" dans un thread a part,
# ce qui evite de bloquer le serveur pendant une requete SQL.
# =====================================================================

@app.post("/adduser", response_model=UserOut)
def add_user(url: Request, request: UserSchema, db: Session = Depends(get_db)):
    user = User(name=request.name, email=request.email, nickname=request.nickname,
                url=user_url(url, request.name))
    db.add(user)
    commit_or_409(db)
    db.refresh(user)
    return user


@app.get("/users", response_model=list[UserOut])
def get_users(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).all()
    for user in users:
        user.url = user_url(request, user.name)
    return users


@app.get("/user/{user_name}", response_model=UserWithPosts)
def get_user(user_name: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.name == user_name).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user


@app.delete("/user/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    db.delete(user)
    db.commit()
    return {"message": f"Utilisateur {user_id} supprimé avec succès"}


@app.put("/user/{user_id}", response_model=UserOut)
def update_user(url: Request, user_id: int, request: UserSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.name = request.name
    user.email = request.email
    user.nickname = request.nickname
    user.url = user_url(url, request.name)
    commit_or_409(db)
    db.refresh(user)
    return user


# =====================================================================
# Posts (exercice) : un utilisateur a plusieurs posts, un post a un seul
# auteur.
# =====================================================================

def get_post_or_404(post_id: int, db: Session) -> Post:
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post non trouvé")
    return post


@app.post("/addpost", response_model=PostOut)
def add_post(request: PostCreate, db: Session = Depends(get_db)):
    if not db.query(User).filter(User.id == request.user_id).first():
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    post = Post(title=request.title, content=request.content, user_id=request.user_id)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@app.get("/posts", response_model=list[PostOut])
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).all()


@app.get("/post/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    return get_post_or_404(post_id, db)


@app.get("/user/{user_id}/posts", response_model=list[PostOut])
def get_user_posts(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user.posts


@app.put("/post/{post_id}", response_model=PostOut)
def update_post(post_id: int, request: PostUpdate, db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    post.title = request.title
    post.content = request.content
    db.commit()
    db.refresh(post)
    return post


@app.delete("/post/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    db.delete(post)
    db.commit()
    return {"message": f"Post {post_id} supprimé avec succès"}
