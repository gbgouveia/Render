from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from paprica import get_db_connection


# =========================
# FUNÇÕES AUXILIARES
# =========================
def fetch_one(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def fetch_all(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def execute_query(query, params=None, commit=True, returning=False):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        result = cur.fetchone() if returning else None
        if commit:
            conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# =========================
# USUÁRIO
# =========================
class User(UserMixin):
    def __init__(
        self,
        id,
        usuario,
        email,
        senha=None,
        google_id=None,
        avatar=None,
        role="cliente",
        is_admin=False,
        data_criacao=None
    ):
        self.id = id
        self.usuario = usuario
        self.email = email
        self.senha = senha
        self.google_id = google_id
        self.avatar = avatar
        self.role = role
        self.is_admin = is_admin
        self.data_criacao = data_criacao

    def set_senha(self, senha_texto: str) -> None:
        senha_hash = generate_password_hash(senha_texto)
        execute_query(
            """
            UPDATE users
            SET senha = %s
            WHERE id = %s
            """,
            (senha_hash, self.id)
        )
        self.senha = senha_hash

    def check_senha(self, senha_digitada: str) -> bool:
        if not self.senha:
            return False
        return check_password_hash(self.senha, senha_digitada)

    @staticmethod
    def from_row(row):
        if not row:
            return None
        return User(
            id=row["id"],
            usuario=row["usuario"],
            email=row["email"],
            senha=row.get("senha"),
            google_id=row.get("google_id"),
            avatar=row.get("avatar"),
            role=row.get("role", "cliente"),
            is_admin=row.get("is_admin", False),
            data_criacao=row.get("data_criacao"),
        )

    @staticmethod
    def get_by_id(user_id: int):
        row = fetch_one(
            """
            SELECT id, usuario, email, senha, google_id, avatar, role, is_admin, data_criacao
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )
        return User.from_row(row)

    @staticmethod
    def get_by_email(email: str):
        row = fetch_one(
            """
            SELECT id, usuario, email, senha, google_id, avatar, role, is_admin, data_criacao
            FROM users
            WHERE email = %s
            """,
            (email,)
        )
        return User.from_row(row)

    @staticmethod
    def get_by_usuario(usuario: str):
        row = fetch_one(
            """
            SELECT id, usuario, email, senha, google_id, avatar, role, is_admin, data_criacao
            FROM users
            WHERE usuario = %s
            """,
            (usuario,)
        )
        return User.from_row(row)

    @staticmethod
    def get_by_google_id(google_id: str):
        row = fetch_one(
            """
            SELECT id, usuario, email, senha, google_id, avatar, role, is_admin, data_criacao
            FROM users
            WHERE google_id = %s
            """,
            (google_id,)
        )
        return User.from_row(row)

    @staticmethod
    def create(usuario, email, senha=None, google_id=None, avatar=None, role="cliente", is_admin=False):
        senha_hash = generate_password_hash(senha) if senha else None

        row = execute_query(
            """
            INSERT INTO users (usuario, email, senha, google_id, avatar, role, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, usuario, email, senha, google_id, avatar, role, is_admin, data_criacao
            """,
            (usuario, email, senha_hash, google_id, avatar, role, is_admin),
            returning=True
        )
        return User.from_row(row)


# =========================
# CATEGORIAS
# =========================
class Categoria:
    @staticmethod
    def all():
        return fetch_all(
            """
            SELECT id, nome, slug, imagem, data_criacao
            FROM categorias
            ORDER BY nome ASC
            """
        )

    @staticmethod
    def get_by_id(categoria_id):
        return fetch_one(
            """
            SELECT id, nome, slug, imagem, data_criacao
            FROM categorias
            WHERE id = %s
            """,
            (categoria_id,)
        )

    @staticmethod
    def get_by_slug(slug):
        return fetch_one(
            """
            SELECT id, nome, slug, imagem, data_criacao
            FROM categorias
            WHERE slug = %s
            """,
            (slug,)
        )


# =========================
# MARCAS
# =========================
class Marca:
    @staticmethod
    def all():
        return fetch_all(
            """
            SELECT id, nome, slug, logo, data_criacao
            FROM marcas
            ORDER BY nome ASC
            """
        )

    @staticmethod
    def get_by_id(marca_id):
        return fetch_one(
            """
            SELECT id, nome, slug, logo, data_criacao
            FROM marcas
            WHERE id = %s
            """,
            (marca_id,)
        )

    @staticmethod
    def get_by_slug(slug):
        return fetch_one(
            """
            SELECT id, nome, slug, logo, data_criacao
            FROM marcas
            WHERE slug = %s
            """,
            (slug,)
        )


# =========================
# ENDEREÇOS
# =========================
class Endereco:
    @staticmethod
    def get_by_user(usuario_id):
        return fetch_all(
            """
            SELECT *
            FROM enderecos
            WHERE usuario_id = %s
            ORDER BY principal DESC, id DESC
            """,
            (usuario_id,)
        )

    @staticmethod
    def get_by_id(endereco_id):
        return fetch_one(
            """
            SELECT *
            FROM enderecos
            WHERE id = %s
            """,
            (endereco_id,)
        )


# =========================
# PRODUTOS
# =========================
class Item:
    @staticmethod
    def all():
        return fetch_all(
            """
            SELECT *
            FROM itens
            ORDER BY id DESC
            """
        )

    @staticmethod
    def ativos():
        return fetch_all(
            """
            SELECT *
            FROM itens
            WHERE ativo = TRUE
            ORDER BY id DESC
            """
        )

    @staticmethod
    def get_by_id(item_id):
        return fetch_one(
            """
            SELECT *
            FROM itens
            WHERE id = %s
            """,
            (item_id,)
        )

    @staticmethod
    def get_by_categoria(categoria_id):
        return fetch_all(
            """
            SELECT *
            FROM itens
            WHERE categoria_id = %s AND ativo = TRUE
            ORDER BY id DESC
            """,
            (categoria_id,)
        )

    @staticmethod
    def get_by_marca(marca_id):
        return fetch_all(
            """
            SELECT *
            FROM itens
            WHERE marca_id = %s AND ativo = TRUE
            ORDER BY id DESC
            """,
            (marca_id,)
        )


class ItemImagem:
    @staticmethod
    def get_by_item(item_id):
        return fetch_all(
            """
            SELECT *
            FROM itens_imagens
            WHERE item_id = %s
            ORDER BY id DESC
            """,
            (item_id,)
        )


# =========================
# CARRINHO
# =========================
class ItemCarrinho:
    @staticmethod
    def get_by_user(usuario_id):
        return fetch_all(
            """
            SELECT
                ic.id,
                ic.usuario_id,
                ic.item_id,
                ic.quantidade,
                i.nome,
                i.preco,
                i.imagem,
                i.estoque,
                i.ativo
            FROM itens_carrinho ic
            INNER JOIN itens i ON i.id = ic.item_id
            WHERE ic.usuario_id = %s
            ORDER BY ic.id DESC
            """,
            (usuario_id,)
        )

    @staticmethod
    def get_item(usuario_id, item_id):
        return fetch_one(
            """
            SELECT *
            FROM itens_carrinho
            WHERE usuario_id = %s AND item_id = %s
            """,
            (usuario_id, item_id)
        )


# =========================
# PEDIDO
# =========================
class Pedido:
    @staticmethod
    def get_by_id(pedido_id):
        return fetch_one(
            """
            SELECT *
            FROM pedidos
            WHERE id = %s
            """,
            (pedido_id,)
        )

    @staticmethod
    def get_by_user(usuario_id):
        return fetch_all(
            """
            SELECT *
            FROM pedidos
            WHERE usuario_id = %s
            ORDER BY id DESC
            """,
            (usuario_id,)
        )


# =========================
# ITENS DO PEDIDO
# =========================
class ItemPedido:
    @staticmethod
    def get_by_pedido(pedido_id):
        return fetch_all(
            """
            SELECT *
            FROM itens_pedido
            WHERE pedido_id = %s
            ORDER BY id ASC
            """,
            (pedido_id,)
        )


# =========================
# FAVORITOS
# =========================
class Favorito:
    @staticmethod
    def get_by_user(usuario_id):
        return fetch_all(
            """
            SELECT
                f.id,
                f.usuario_id,
                f.item_id,
                i.nome,
                i.preco,
                i.imagem,
                i.ativo
            FROM favoritos f
            INNER JOIN itens i ON i.id = f.item_id
            WHERE f.usuario_id = %s
            ORDER BY f.id DESC
            """,
            (usuario_id,)
        )

    @staticmethod
    def exists(usuario_id, item_id):
        return fetch_one(
            """
            SELECT id
            FROM favoritos
            WHERE usuario_id = %s AND item_id = %s
            """,
            (usuario_id, item_id)
        )


# =========================
# BANNERS
# =========================
class Banner:
    @staticmethod
    def ativos():
        return fetch_all(
            """
            SELECT *
            FROM banners
            WHERE ativo = TRUE
            ORDER BY ordem ASC, id DESC
            """
        )

    @staticmethod
    def all():
        return fetch_all(
            """
            SELECT *
            FROM banners
            ORDER BY ordem ASC, id DESC
            """
        )