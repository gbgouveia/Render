from paprica import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint


# =========================
# USUÁRIO
# =========================
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    usuario = db.Column(db.String(30), nullable=False, unique=True)
    email = db.Column(db.String(345), nullable=False, unique=True)
    senha = db.Column(db.String(255), nullable=True)

    google_id = db.Column(db.String(255), unique=True, nullable=True)
    avatar = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(20), default="cliente")
    is_admin = db.Column(db.Boolean, default=False)

    data_criacao = db.Column(db.DateTime, default=db.func.now())

    enderecos = db.relationship("Endereco", backref="usuario", cascade="all, delete-orphan")
    carrinho = db.relationship("ItemCarrinho", backref="usuario", cascade="all, delete-orphan")
    pedidos = db.relationship("Pedido", backref="usuario", cascade="all, delete-orphan")
    favoritos = db.relationship("Favorito", backref="usuario", cascade="all, delete-orphan")

    def set_senha(self, senha_texto: str) -> None:
        self.senha = generate_password_hash(senha_texto)

    def check_senha(self, senha_digitada: str) -> bool:
        if not self.senha:
            return False
        return check_password_hash(self.senha, senha_digitada)

# =========================
# CATEGORIAS
# =========================
class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(120), nullable=False, unique=True)
    imagem = db.Column(db.String(200), nullable=True)

    data_criacao = db.Column(db.DateTime, default=db.func.now())

    produtos = db.relationship("Item", backref="categoria", lazy=True)

# =========================
# MARCAS
# =========================
class Marca(db.Model):
    __tablename__ = "marcas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(120), nullable=False, unique=True)
    logo = db.Column(db.String(200), nullable=True)

    data_criacao = db.Column(db.DateTime, default=db.func.now())

    produtos = db.relationship("Item", backref="marca", lazy=True)



# =========================
# ENDEREÇOS
# =========================
class Endereco(db.Model):
    __tablename__ = "enderecos"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    cep = db.Column(db.String(8), nullable=False)
    rua = db.Column(db.String(150), nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    complemento = db.Column(db.String(150))
    bairro = db.Column(db.String(100), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(2), nullable=False)

    principal = db.Column(db.Boolean, default=False)
    data_criacao = db.Column(db.DateTime, default=db.func.now())


# =========================
# PRODUTOS
# =========================
class Item(db.Model):
    __tablename__ = "itens"

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.Text, nullable=False)

    preco = db.Column(db.Numeric(10, 2), nullable=False)
    estoque = db.Column(db.Integer, default=0)

    ativo = db.Column(db.Boolean, default=True)

    imagem = db.Column(db.String(200))
    cod_barra = db.Column(db.String(50), unique=True)

    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=True)
    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.id"), nullable=True)

    peso = db.Column(db.Float, nullable=False)
    altura = db.Column(db.Float, nullable=False)
    largura = db.Column(db.Float, nullable=False)
    comprimento = db.Column(db.Float, nullable=False)

    data_criacao = db.Column(db.DateTime, default=db.func.now())

    imagens = db.relationship(
        "ItemImagem",
        backref="produto",
        cascade="all, delete-orphan",
        order_by="ItemImagem.id.desc()"
    )


class ItemImagem(db.Model):
    __tablename__ = "itens_imagens"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("itens.id", ondelete="CASCADE"), nullable=False)
    arquivo = db.Column(db.String(200), nullable=False)
    data_criacao = db.Column(db.DateTime, default=db.func.now())


# =========================
# CARRINHO
# =========================
class ItemCarrinho(db.Model):
    __tablename__ = "itens_carrinho"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("itens.id", ondelete="CASCADE"), nullable=False)

    quantidade = db.Column(db.Integer, nullable=False, default=1)

    item = db.relationship("Item")

    __table_args__ = (
        UniqueConstraint("usuario_id", "item_id", name="unique_usuario_item"),
    )


# =========================
# PEDIDO
# =========================
class Pedido(db.Model):
    __tablename__ = "pedidos"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    total_produtos = db.Column(db.Numeric(10, 2), nullable=False)
    frete_valor = db.Column(db.Numeric(10, 2), nullable=False)
    total_final = db.Column(db.Numeric(10, 2), nullable=False)

    status = db.Column(db.String(50), default="aguardando_pagamento")

    gateway = db.Column(db.String(50))
    transacao_id = db.Column(db.String(150))
    status_pagamento = db.Column(db.String(50))

    frete_nome = db.Column(db.String(100))
    frete_prazo = db.Column(db.Integer)
    codigo_rastreamento = db.Column(db.String(100))

    cep = db.Column(db.String(8))
    rua = db.Column(db.String(150))
    numero = db.Column(db.String(20))
    complemento = db.Column(db.String(150))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))

    data_criacao = db.Column(db.DateTime, default=db.func.now())

    itens = db.relationship("ItemPedido", backref="pedido", cascade="all, delete-orphan")


# =========================
# ITENS DO PEDIDO
# =========================
class ItemPedido(db.Model):
    __tablename__ = "itens_pedido"

    id = db.Column(db.Integer, primary_key=True)

    pedido_id = db.Column(db.Integer, db.ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("itens.id"), nullable=False)

    nome_produto = db.Column(db.String(150))
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Numeric(10, 2), nullable=False)

    item = db.relationship("Item")


# =========================
# FAVORITOS
# =========================
class Favorito(db.Model):
    __tablename__ = "favoritos"

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    item_id = db.Column(db.Integer, db.ForeignKey("itens.id", ondelete="CASCADE"))

    item = db.relationship("Item")

class Banner(db.Model):
    __tablename__ = "banners"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    imagem = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(300), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    ordem = db.Column(db.Integer, default=0)

    data_criacao = db.Column(db.DateTime, default=db.func.now())