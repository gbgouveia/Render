from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, current_app
from flask_login import login_required, current_user
from paprica import db
from functools import wraps
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
import uuid
import os
import re

from paprica.models import (
    Item,
    User,
    Pedido,
    ItemPedido,
    ItemImagem,
    Categoria,
    Marca,
    Banner
)
from paprica.forms import ProdutoForm, MarcaForm, CategoriaForm, BannerForm

admin = Blueprint("admin", __name__, url_prefix="/admin")


def slugify(texto):
    texto = (texto or "").strip().lower()
    texto = re.sub(r"[^\w\s-]", "", texto)
    texto = re.sub(r"[\s_-]+", "-", texto)
    texto = re.sub(r"^-+|-+$", "", texto)
    return texto


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


def _allowed(filename: str) -> bool:
    if not filename:
        return False
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _save_upload(file_storage):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    if not _allowed(file_storage.filename):
        return None

    nome_arquivo = secure_filename(file_storage.filename)
    nome_final = f"{uuid.uuid4().hex}_{nome_arquivo}"

    upload_folder = current_app.config.get("UPLOAD_FOLDER")
    if not upload_folder:
        upload_folder = os.path.join("paprica", "static", "uploads")

    os.makedirs(upload_folder, exist_ok=True)
    caminho = os.path.join(upload_folder, nome_final)
    file_storage.save(caminho)

    return nome_final


def _delete_file_if_exists(filename: str):
    if not filename:
        return

    upload_folder = current_app.config.get("UPLOAD_FOLDER") or os.path.join("paprica", "static", "uploads")
    caminho = os.path.join(upload_folder, filename)

    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except Exception:
        pass


def _montar_choices_produto_form(form):
    categorias = Categoria.query.order_by(Categoria.nome.asc()).all()
    marcas = Marca.query.order_by(Marca.nome.asc()).all()

    form.categoria_id.choices = [(0, "Selecione uma categoria")] + [(c.id, c.nome) for c in categorias]
    form.marca_id.choices = [(0, "Selecione uma marca")] + [(m.id, m.nome) for m in marcas]


# =========================
# DASHBOARD
# =========================
@admin.route("/")
@login_required
@admin_required
def dashboard():
    total_produtos = Item.query.count()
    total_usuarios = User.query.count()
    total_pedidos = Pedido.query.count()
    total_categorias = Categoria.query.count()
    total_marcas = Marca.query.count()

    return render_template(
        "admin/dashboard.html",
        total_produtos=total_produtos,
        total_usuarios=total_usuarios,
        total_pedidos=total_pedidos,
        total_categorias=total_categorias,
        total_marcas=total_marcas
    )


# =========================
# CATEGORIAS
# =========================
@admin.route("/categorias")
@login_required
@admin_required
def categorias():
    categorias = Categoria.query.order_by(Categoria.nome.asc()).all()
    form = CategoriaForm()
    return render_template("admin/categorias.html", categorias=categorias, form=form)


@admin.route("/categorias/criar", methods=["POST"])
@login_required
@admin_required
def criar_categoria():
    form = CategoriaForm()

    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
        return redirect(url_for("admin.categorias"))

    nome = (form.nome.data or "").strip()
    slug = slugify(nome)

    existe = Categoria.query.filter(
        db.or_(Categoria.nome == nome, Categoria.slug == slug)
    ).first()

    if existe:
        flash("Essa categoria já existe.", "warning")
        return redirect(url_for("admin.categorias"))

    imagem_nome = None
    if form.imagem.data and getattr(form.imagem.data, "filename", ""):
        imagem_nome = _save_upload(form.imagem.data)
        if not imagem_nome:
            flash("Imagem da categoria inválida.", "danger")
            return redirect(url_for("admin.categorias"))

    nova_categoria = Categoria(
        nome=nome,
        slug=slug,
        imagem=imagem_nome
    )

    db.session.add(nova_categoria)
    db.session.commit()

    flash("Categoria criada com sucesso!", "success")
    return redirect(url_for("admin.categorias"))


@admin.route("/categorias/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_categoria(id):
    categoria = Categoria.query.get_or_404(id)

    if categoria.produtos:
        flash("Não é possível excluir uma categoria que possui produtos.", "danger")
        return redirect(url_for("admin.categorias"))

    if categoria.imagem:
        _delete_file_if_exists(categoria.imagem)

    db.session.delete(categoria)
    db.session.commit()

    flash("Categoria excluída com sucesso!", "info")
    return redirect(url_for("admin.categorias"))


# =========================
# MARCAS
# =========================
@admin.route("/marcas")
@login_required
@admin_required
def marcas():
    marcas = Marca.query.order_by(Marca.nome.asc()).all()
    form = MarcaForm()
    return render_template("admin/marcas.html", marcas=marcas, form=form)


@admin.route("/marcas/criar", methods=["POST"])
@login_required
@admin_required
def criar_marca():
    form = MarcaForm()

    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
        return redirect(url_for("admin.marcas"))

    nome = (form.nome.data or "").strip()
    slug = slugify(nome)

    existe = Marca.query.filter(
        db.or_(Marca.nome == nome, Marca.slug == slug)
    ).first()

    if existe:
        flash("Essa marca já existe.", "warning")
        return redirect(url_for("admin.marcas"))

    logo_nome = None
    if form.logo.data and getattr(form.logo.data, "filename", ""):
        logo_nome = _save_upload(form.logo.data)
        if not logo_nome:
            flash("Logo inválida.", "danger")
            return redirect(url_for("admin.marcas"))

    nova_marca = Marca(
        nome=nome,
        slug=slug,
        logo=logo_nome
    )

    db.session.add(nova_marca)
    db.session.commit()

    flash("Marca criada com sucesso!", "success")
    return redirect(url_for("admin.marcas"))


@admin.route("/marcas/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_marca(id):
    marca = Marca.query.get_or_404(id)

    if marca.produtos:
        flash("Não é possível excluir uma marca que possui produtos.", "danger")
        return redirect(url_for("admin.marcas"))

    if marca.logo:
        _delete_file_if_exists(marca.logo)

    db.session.delete(marca)
    db.session.commit()

    flash("Marca excluída com sucesso!", "info")
    return redirect(url_for("admin.marcas"))


# =========================
# BANNERS
# =========================
@admin.route("/banners")
@login_required
@admin_required
def banners():
    banners = Banner.query.order_by(Banner.ordem.asc(), Banner.id.desc()).all()
    form = BannerForm()
    return render_template("admin/banners.html", banners=banners, form=form)


@admin.route("/banners/criar", methods=["POST"])
@login_required
@admin_required
def criar_banner():
    form = BannerForm()

    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "danger")
        return redirect(url_for("admin.banners"))

    imagem_nome = _save_upload(form.imagem.data)
    if not imagem_nome:
        flash("Imagem do banner inválida.", "danger")
        return redirect(url_for("admin.banners"))

    banner = Banner(
        titulo=(form.titulo.data or "").strip(),
        imagem=imagem_nome,
        link=(form.link.data or "").strip() or None,
        ordem=form.ordem.data or 0,
        ativo=form.ativo.data
    )

    db.session.add(banner)
    db.session.commit()

    flash("Banner criado com sucesso!", "success")
    return redirect(url_for("admin.banners"))


@admin.route("/banners/toggle/<int:id>", methods=["POST"])
@login_required
@admin_required
def toggle_banner(id):
    banner = Banner.query.get_or_404(id)
    banner.ativo = not banner.ativo
    db.session.commit()

    flash("Status do banner atualizado.", "success")
    return redirect(url_for("admin.banners"))


@admin.route("/banners/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_banner(id):
    banner = Banner.query.get_or_404(id)

    if banner.imagem:
        _delete_file_if_exists(banner.imagem)

    db.session.delete(banner)
    db.session.commit()

    flash("Banner excluído com sucesso!", "info")
    return redirect(url_for("admin.banners"))


# =========================
# PRODUTOS
# =========================
@admin.route("/produtos")
@login_required
@admin_required
def produtos():
    itens = Item.query.order_by(Item.data_criacao.desc()).all()
    return render_template("admin/produtos.html", itens=itens)


@admin.route("/criar-produto", methods=["GET", "POST"])
@login_required
@admin_required
def criar_produto():
    form = ProdutoForm()
    _montar_choices_produto_form(form)

    if request.method == "POST":
        print("FORM ERRORS:", form.errors)

    if form.validate_on_submit():
        try:
            novo = Item(
                nome=form.nome.data,
                descricao=form.descricao.data or "",
                preco=form.preco.data,
                estoque=form.estoque.data,
                ativo=True,
                cod_barra=form.cod_barra.data.strip() if form.cod_barra.data else None,
                categoria_id=form.categoria_id.data if form.categoria_id.data != 0 else None,
                marca_id=form.marca_id.data if form.marca_id.data != 0 else None,
                peso=form.peso.data,
                altura=form.altura.data,
                largura=form.largura.data,
                comprimento=form.comprimento.data
            )

            if form.imagem.data and getattr(form.imagem.data, "filename", ""):
                nome_final = _save_upload(form.imagem.data)
                if not nome_final:
                    flash("Imagem principal inválida.", "danger")
                    return render_template("admin/novo_produto.html", form=form)

                novo.imagem = nome_final

            db.session.add(novo)
            db.session.flush()

            if hasattr(form, "imagens") and form.imagens.data:
                for arquivo in form.imagens.data:
                    if not arquivo or not getattr(arquivo, "filename", ""):
                        continue

                    nome_img = _save_upload(arquivo)
                    if nome_img:
                        db.session.add(ItemImagem(item_id=novo.id, arquivo=nome_img))

            db.session.commit()
            flash("Produto criado com sucesso!", "success")
            return redirect(url_for("admin.produtos"))

        except IntegrityError:
            db.session.rollback()
            flash("Erro ao salvar produto. Verifique se o código de barras já existe.", "danger")

        except Exception as e:
            db.session.rollback()
            print("ERRO AO CRIAR PRODUTO:", e)
            flash(f"Erro inesperado ao salvar produto: {e}", "danger")

    return render_template("admin/novo_produto.html", form=form)


@admin.route("/produto/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_produto(id):
    produto = Item.query.get_or_404(id)
    form = ProdutoForm(obj=produto)
    _montar_choices_produto_form(form)

    if request.method == "GET":
        form.categoria_id.data = produto.categoria_id or 0
        form.marca_id.data = produto.marca_id or 0

    if form.validate_on_submit():
        try:
            produto.nome = form.nome.data
            produto.preco = form.preco.data
            produto.estoque = form.estoque.data
            produto.descricao = form.descricao.data or ""
            produto.cod_barra = form.cod_barra.data.strip() if form.cod_barra.data else None
            produto.categoria_id = form.categoria_id.data if form.categoria_id.data != 0 else None
            produto.marca_id = form.marca_id.data if form.marca_id.data != 0 else None
            produto.peso = form.peso.data
            produto.altura = form.altura.data
            produto.largura = form.largura.data
            produto.comprimento = form.comprimento.data

            if form.imagem.data and getattr(form.imagem.data, "filename", ""):
                nome_final = _save_upload(form.imagem.data)
                if not nome_final:
                    flash("Imagem principal inválida.", "danger")
                    return render_template("admin/editar_produto.html", form=form, produto=produto, imagens=produto.imagens)

                _delete_file_if_exists(produto.imagem)
                produto.imagem = nome_final

            if hasattr(form, "imagens") and form.imagens.data:
                for arquivo in form.imagens.data:
                    if not arquivo or not getattr(arquivo, "filename", ""):
                        continue

                    nome_img = _save_upload(arquivo)
                    if nome_img:
                        db.session.add(ItemImagem(item_id=produto.id, arquivo=nome_img))

            db.session.commit()
            flash("Produto atualizado!", "success")
            return redirect(url_for("admin.produtos"))

        except IntegrityError:
            db.session.rollback()
            flash("Erro ao atualizar produto. Código de barras pode estar duplicado.", "danger")

    imagens = ItemImagem.query.filter_by(item_id=produto.id).order_by(ItemImagem.id.desc()).all()
    return render_template("admin/editar_produto.html", form=form, produto=produto, imagens=imagens)


@admin.route("/produto/imagem/excluir/<int:img_id>", methods=["POST"])
@login_required
@admin_required
def excluir_imagem_produto(img_id):
    img = ItemImagem.query.get_or_404(img_id)
    _delete_file_if_exists(img.arquivo)

    produto_id = img.item_id
    db.session.delete(img)
    db.session.commit()

    flash("Imagem removida da galeria.", "info")
    return redirect(url_for("admin.editar_produto", id=produto_id))


@admin.route("/produto/imagem/definir-principal/<int:img_id>", methods=["POST"])
@login_required
@admin_required
def definir_imagem_principal(img_id):
    img = ItemImagem.query.get_or_404(img_id)
    produto = Item.query.get_or_404(img.item_id)

    produto.imagem = img.arquivo
    db.session.commit()

    flash("Imagem definida como principal.", "success")
    return redirect(url_for("admin.editar_produto", id=produto.id))


@admin.route("/produto/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_produto(id):
    produto = Item.query.get_or_404(id)

    try:
        # verifica se já existe em pedidos
        existe_em_pedido = ItemPedido.query.filter_by(item_id=produto.id).first()

        if existe_em_pedido:
            produto.ativo = False
            db.session.commit()
            flash("Produto desativado com sucesso! Ele não foi apagado porque já existe em pedidos.", "warning")
            return redirect(url_for("admin.produtos"))

        # se nunca foi usado em pedido, pode excluir de verdade
        if produto.imagem:
            _delete_file_if_exists(produto.imagem)

        imagens_extras = ItemImagem.query.filter_by(item_id=produto.id).all()
        for img in imagens_extras:
            if img.arquivo:
                _delete_file_if_exists(img.arquivo)
            db.session.delete(img)

        db.session.delete(produto)
        db.session.commit()

        flash("Produto excluído com sucesso!", "info")

    except Exception as e:
        db.session.rollback()
        print("ERRO AO EXCLUIR PRODUTO:", e)
        flash("Erro ao excluir produto.", "danger")

    return redirect(url_for("admin.produtos"))


# =========================
# USUÁRIOS
# =========================
@admin.route("/usuarios")
@login_required
@admin_required
def usuarios():
    usuarios = User.query.order_by(User.data_criacao.desc()).all()
    total_admins = User.query.filter_by(is_admin=True).count()
    return render_template("admin/usuarios.html", usuarios=usuarios, total_admins=total_admins)


@admin.route("/usuarios/toggle-admin/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Você não pode alterar seu próprio status de admin.", "warning")
        return redirect(url_for("admin.usuarios"))

    if user.is_admin:
        total_admins = User.query.filter_by(is_admin=True).count()
        if total_admins <= 1:
            flash("Você não pode remover o último admin do sistema.", "danger")
            return redirect(url_for("admin.usuarios"))

        user.is_admin = False
        user.role = "cliente"
        flash(f"{user.usuario} agora NÃO é mais admin.", "info")
    else:
        user.is_admin = True
        user.role = "admin"
        flash(f"{user.usuario} agora é ADMIN ✅", "success")

    db.session.commit()
    return redirect(url_for("admin.usuarios"))


# =========================
# PEDIDOS
# =========================
@admin.route("/pedidos")
@login_required
@admin_required
def pedidos():
    pedidos = Pedido.query.order_by(Pedido.data_criacao.desc()).all()
    return render_template("admin/pedidos.html", pedidos=pedidos)


@admin.route("/pedidos/<int:pedido_id>")
@login_required
@admin_required
def pedido_detalhe(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    itens = ItemPedido.query.filter_by(pedido_id=pedido.id).all()
    return render_template("admin/pedido_detalhe.html", pedido=pedido, itens=itens)


@admin.route("/pedidos/<int:pedido_id>/atualizar", methods=["POST"])
@login_required
@admin_required
def pedido_atualizar(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    status = (request.form.get("status") or "").strip()
    rastreio = (request.form.get("codigo_rastreamento") or "").strip()

    status_validos = [
        "aguardando_pagamento",
        "pago",
        "separando",
        "enviado",
        "entregue",
        "cancelado"
    ]

    if status not in status_validos:
        flash("Status inválido.", "danger")
        return redirect(url_for("admin.pedido_detalhe", pedido_id=pedido.id))

    pedido.status = status
    pedido.codigo_rastreamento = rastreio if rastreio else None

    db.session.commit()
    flash("Pedido atualizado com sucesso!", "success")
    return redirect(url_for("admin.pedido_detalhe", pedido_id=pedido.id))

@admin.route("/produto/toggle/<int:id>", methods=["POST"])
@login_required
@admin_required
def toggle_produto(id):
    produto = Item.query.get_or_404(id)
    produto.ativo = not produto.ativo
    db.session.commit()

    if produto.ativo:
        flash("Produto reativado com sucesso!", "success")
    else:
        flash("Produto desativado com sucesso!", "warning")

    return redirect(url_for("admin.produtos"))