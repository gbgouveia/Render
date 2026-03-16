from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, current_app
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename
import uuid
import os
import re

from paprica import get_db_connection
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


def _fetch_one(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def _fetch_all(query, params=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _execute(query, params=None, returning=False):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        result = cur.fetchone() if returning else None
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _montar_choices_produto_form(form):
    categorias = _fetch_all(
        """
        SELECT id, nome
        FROM categorias
        ORDER BY nome ASC
        """
    )
    marcas = _fetch_all(
        """
        SELECT id, nome
        FROM marcas
        ORDER BY nome ASC
        """
    )

    form.categoria_id.choices = [(0, "Selecione uma categoria")] + [(c["id"], c["nome"]) for c in categorias]
    form.marca_id.choices = [(0, "Selecione uma marca")] + [(m["id"], m["nome"]) for m in marcas]


# =========================
# DASHBOARD
# =========================
@admin.route("/")
@login_required
@admin_required
def dashboard():
    total_produtos = _fetch_one("SELECT COUNT(*) AS total FROM itens")["total"]
    total_usuarios = _fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
    total_pedidos = _fetch_one("SELECT COUNT(*) AS total FROM pedidos")["total"]
    total_categorias = _fetch_one("SELECT COUNT(*) AS total FROM categorias")["total"]
    total_marcas = _fetch_one("SELECT COUNT(*) AS total FROM marcas")["total"]

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
    categorias = _fetch_all(
        """
        SELECT *
        FROM categorias
        ORDER BY nome ASC
        """
    )
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

    existe = _fetch_one(
        """
        SELECT id
        FROM categorias
        WHERE nome = %s OR slug = %s
        LIMIT 1
        """,
        (nome, slug)
    )

    if existe:
        flash("Essa categoria já existe.", "warning")
        return redirect(url_for("admin.categorias"))

    imagem_nome = None
    if form.imagem.data and getattr(form.imagem.data, "filename", ""):
        imagem_nome = _save_upload(form.imagem.data)
        if not imagem_nome:
            flash("Imagem da categoria inválida.", "danger")
            return redirect(url_for("admin.categorias"))

    _execute(
        """
        INSERT INTO categorias (nome, slug, imagem)
        VALUES (%s, %s, %s)
        """,
        (nome, slug, imagem_nome)
    )

    flash("Categoria criada com sucesso!", "success")
    return redirect(url_for("admin.categorias"))


@admin.route("/categorias/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_categoria(id):
    categoria = _fetch_one(
        """
        SELECT *
        FROM categorias
        WHERE id = %s
        """,
        (id,)
    )

    if not categoria:
        abort(404)

    possui_produtos = _fetch_one(
        """
        SELECT id
        FROM itens
        WHERE categoria_id = %s
        LIMIT 1
        """,
        (id,)
    )

    if possui_produtos:
        flash("Não é possível excluir uma categoria que possui produtos.", "danger")
        return redirect(url_for("admin.categorias"))

    if categoria.get("imagem"):
        _delete_file_if_exists(categoria["imagem"])

    _execute(
        """
        DELETE FROM categorias
        WHERE id = %s
        """,
        (id,)
    )

    flash("Categoria excluída com sucesso!", "info")
    return redirect(url_for("admin.categorias"))


# =========================
# MARCAS
# =========================
@admin.route("/marcas")
@login_required
@admin_required
def marcas():
    marcas = _fetch_all(
        """
        SELECT *
        FROM marcas
        ORDER BY nome ASC
        """
    )
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

    existe = _fetch_one(
        """
        SELECT id
        FROM marcas
        WHERE nome = %s OR slug = %s
        LIMIT 1
        """,
        (nome, slug)
    )

    if existe:
        flash("Essa marca já existe.", "warning")
        return redirect(url_for("admin.marcas"))

    logo_nome = None
    if form.logo.data and getattr(form.logo.data, "filename", ""):
        logo_nome = _save_upload(form.logo.data)
        if not logo_nome:
            flash("Logo inválida.", "danger")
            return redirect(url_for("admin.marcas"))

    _execute(
        """
        INSERT INTO marcas (nome, slug, logo)
        VALUES (%s, %s, %s)
        """,
        (nome, slug, logo_nome)
    )

    flash("Marca criada com sucesso!", "success")
    return redirect(url_for("admin.marcas"))


@admin.route("/marcas/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_marca(id):
    marca = _fetch_one(
        """
        SELECT *
        FROM marcas
        WHERE id = %s
        """,
        (id,)
    )

    if not marca:
        abort(404)

    possui_produtos = _fetch_one(
        """
        SELECT id
        FROM itens
        WHERE marca_id = %s
        LIMIT 1
        """,
        (id,)
    )

    if possui_produtos:
        flash("Não é possível excluir uma marca que possui produtos.", "danger")
        return redirect(url_for("admin.marcas"))

    if marca.get("logo"):
        _delete_file_if_exists(marca["logo"])

    _execute(
        """
        DELETE FROM marcas
        WHERE id = %s
        """,
        (id,)
    )

    flash("Marca excluída com sucesso!", "info")
    return redirect(url_for("admin.marcas"))


# =========================
# BANNERS
# =========================
@admin.route("/banners")
@login_required
@admin_required
def banners():
    banners = _fetch_all(
        """
        SELECT *
        FROM banners
        ORDER BY ordem ASC, id DESC
        """
    )
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

    _execute(
        """
        INSERT INTO banners (titulo, imagem, link, ativo, ordem)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            (form.titulo.data or "").strip(),
            imagem_nome,
            (form.link.data or "").strip() or None,
            form.ativo.data,
            form.ordem.data or 0
        )
    )

    flash("Banner criado com sucesso!", "success")
    return redirect(url_for("admin.banners"))


@admin.route("/banners/toggle/<int:id>", methods=["POST"])
@login_required
@admin_required
def toggle_banner(id):
    banner = _fetch_one(
        """
        SELECT *
        FROM banners
        WHERE id = %s
        """,
        (id,)
    )

    if not banner:
        abort(404)

    _execute(
        """
        UPDATE banners
        SET ativo = %s
        WHERE id = %s
        """,
        (not banner["ativo"], id)
    )

    flash("Status do banner atualizado.", "success")
    return redirect(url_for("admin.banners"))


@admin.route("/banners/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_banner(id):
    banner = _fetch_one(
        """
        SELECT *
        FROM banners
        WHERE id = %s
        """,
        (id,)
    )

    if not banner:
        abort(404)

    if banner.get("imagem"):
        _delete_file_if_exists(banner["imagem"])

    _execute(
        """
        DELETE FROM banners
        WHERE id = %s
        """,
        (id,)
    )

    flash("Banner excluído com sucesso!", "info")
    return redirect(url_for("admin.banners"))


# =========================
# PRODUTOS
# =========================
@admin.route("/produtos")
@login_required
@admin_required
def produtos():
    itens = _fetch_all(
        """
        SELECT i.*, c.nome AS categoria_nome, m.nome AS marca_nome
        FROM itens i
        LEFT JOIN categorias c ON c.id = i.categoria_id
        LEFT JOIN marcas m ON m.id = i.marca_id
        ORDER BY i.data_criacao DESC
        """
    )
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
        conn = get_db_connection()
        cur = conn.cursor()

        imagem_principal_salva = None
        imagens_extras_salvas = []

        try:
            cod_barra = form.cod_barra.data.strip() if form.cod_barra.data else None

            if cod_barra:
                existe_cod = _fetch_one(
                    """
                    SELECT id
                    FROM itens
                    WHERE cod_barra = %s
                    LIMIT 1
                    """,
                    (cod_barra,)
                )
                if existe_cod:
                    flash("Erro ao salvar produto. Verifique se o código de barras já existe.", "danger")
                    return render_template("admin/novo_produto.html", form=form)

            if form.imagem.data and getattr(form.imagem.data, "filename", ""):
                imagem_principal_salva = _save_upload(form.imagem.data)
                if not imagem_principal_salva:
                    flash("Imagem principal inválida.", "danger")
                    return render_template("admin/novo_produto.html", form=form)

            cur.execute(
                """
                INSERT INTO itens (
                    nome, descricao, preco, estoque, ativo, imagem,
                    cod_barra, categoria_id, marca_id,
                    peso, altura, largura, comprimento
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    form.nome.data,
                    form.descricao.data or "",
                    form.preco.data,
                    form.estoque.data,
                    True,
                    imagem_principal_salva,
                    cod_barra,
                    form.categoria_id.data if form.categoria_id.data != 0 else None,
                    form.marca_id.data if form.marca_id.data != 0 else None,
                    form.peso.data,
                    form.altura.data,
                    form.largura.data,
                    form.comprimento.data
                )
            )

            novo_id = cur.fetchone()["id"]

            if hasattr(form, "imagens") and form.imagens.data:
                for arquivo in form.imagens.data:
                    if not arquivo or not getattr(arquivo, "filename", ""):
                        continue

                    nome_img = _save_upload(arquivo)
                    if nome_img:
                        imagens_extras_salvas.append(nome_img)
                        cur.execute(
                            """
                            INSERT INTO itens_imagens (item_id, arquivo)
                            VALUES (%s, %s)
                            """,
                            (novo_id, nome_img)
                        )

            conn.commit()
            flash("Produto criado com sucesso!", "success")
            return redirect(url_for("admin.produtos"))

        except Exception as e:
            conn.rollback()

            if imagem_principal_salva:
                _delete_file_if_exists(imagem_principal_salva)

            for img in imagens_extras_salvas:
                _delete_file_if_exists(img)

            print("ERRO AO CRIAR PRODUTO:", e)
            flash(f"Erro inesperado ao salvar produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

    return render_template("admin/novo_produto.html", form=form)


@admin.route("/produto/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_produto(id):
    produto = _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (id,)
    )

    if not produto:
        abort(404)

    if request.method == "GET":
        form = ProdutoForm(data={
            "nome": produto["nome"],
            "descricao": produto["descricao"],
            "preco": produto["preco"],
            "estoque": produto["estoque"],
            "cod_barra": produto["cod_barra"],
            "categoria_id": produto["categoria_id"] or 0,
            "marca_id": produto["marca_id"] or 0,
            "peso": produto["peso"],
            "altura": produto["altura"],
            "largura": produto["largura"],
            "comprimento": produto["comprimento"],
        })
    else:
        form = ProdutoForm()

    _montar_choices_produto_form(form)

    if form.validate_on_submit():
        conn = get_db_connection()
        cur = conn.cursor()

        nova_imagem_principal = None
        novas_imagens_extras = []

        try:
            cod_barra = form.cod_barra.data.strip() if form.cod_barra.data else None

            if cod_barra:
                existe_cod = _fetch_one(
                    """
                    SELECT id
                    FROM itens
                    WHERE cod_barra = %s AND id <> %s
                    LIMIT 1
                    """,
                    (cod_barra, id)
                )
                if existe_cod:
                    flash("Erro ao atualizar produto. Código de barras pode estar duplicado.", "danger")
                    imagens = _fetch_all(
                        """
                        SELECT *
                        FROM itens_imagens
                        WHERE item_id = %s
                        ORDER BY id DESC
                        """,
                        (id,)
                    )
                    return render_template("admin/editar_produto.html", form=form, produto=produto, imagens=imagens)

            imagem_para_salvar = produto["imagem"]

            if form.imagem.data and getattr(form.imagem.data, "filename", ""):
                nova_imagem_principal = _save_upload(form.imagem.data)
                if not nova_imagem_principal:
                    flash("Imagem principal inválida.", "danger")
                    imagens = _fetch_all(
                        """
                        SELECT *
                        FROM itens_imagens
                        WHERE item_id = %s
                        ORDER BY id DESC
                        """,
                        (id,)
                    )
                    return render_template("admin/editar_produto.html", form=form, produto=produto, imagens=imagens)

                imagem_para_salvar = nova_imagem_principal

            cur.execute(
                """
                UPDATE itens
                SET nome = %s,
                    preco = %s,
                    estoque = %s,
                    descricao = %s,
                    cod_barra = %s,
                    categoria_id = %s,
                    marca_id = %s,
                    peso = %s,
                    altura = %s,
                    largura = %s,
                    comprimento = %s,
                    imagem = %s
                WHERE id = %s
                """,
                (
                    form.nome.data,
                    form.preco.data,
                    form.estoque.data,
                    form.descricao.data or "",
                    cod_barra,
                    form.categoria_id.data if form.categoria_id.data != 0 else None,
                    form.marca_id.data if form.marca_id.data != 0 else None,
                    form.peso.data,
                    form.altura.data,
                    form.largura.data,
                    form.comprimento.data,
                    imagem_para_salvar,
                    id
                )
            )

            if hasattr(form, "imagens") and form.imagens.data:
                for arquivo in form.imagens.data:
                    if not arquivo or not getattr(arquivo, "filename", ""):
                        continue

                    nome_img = _save_upload(arquivo)
                    if nome_img:
                        novas_imagens_extras.append(nome_img)
                        cur.execute(
                            """
                            INSERT INTO itens_imagens (item_id, arquivo)
                            VALUES (%s, %s)
                            """,
                            (id, nome_img)
                        )

            conn.commit()

            if nova_imagem_principal and produto.get("imagem"):
                _delete_file_if_exists(produto["imagem"])

            flash("Produto atualizado!", "success")
            return redirect(url_for("admin.produtos"))

        except Exception as e:
            conn.rollback()

            if nova_imagem_principal:
                _delete_file_if_exists(nova_imagem_principal)

            for img in novas_imagens_extras:
                _delete_file_if_exists(img)

            print("ERRO AO ATUALIZAR PRODUTO:", e)
            flash(f"Erro ao atualizar produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

    imagens = _fetch_all(
        """
        SELECT *
        FROM itens_imagens
        WHERE item_id = %s
        ORDER BY id DESC
        """,
        (id,)
    )

    produto_atualizado = _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (id,)
    )

    return render_template("admin/editar_produto.html", form=form, produto=produto_atualizado, imagens=imagens)


@admin.route("/produto/imagem/excluir/<int:img_id>", methods=["POST"])
@login_required
@admin_required
def excluir_imagem_produto(img_id):
    img = _fetch_one(
        """
        SELECT *
        FROM itens_imagens
        WHERE id = %s
        """,
        (img_id,)
    )

    if not img:
        abort(404)

    if img.get("arquivo"):
        _delete_file_if_exists(img["arquivo"])

    produto_id = img["item_id"]

    _execute(
        """
        DELETE FROM itens_imagens
        WHERE id = %s
        """,
        (img_id,)
    )

    flash("Imagem removida da galeria.", "info")
    return redirect(url_for("admin.editar_produto", id=produto_id))


@admin.route("/produto/imagem/definir-principal/<int:img_id>", methods=["POST"])
@login_required
@admin_required
def definir_imagem_principal(img_id):
    img = _fetch_one(
        """
        SELECT *
        FROM itens_imagens
        WHERE id = %s
        """,
        (img_id,)
    )

    if not img:
        abort(404)

    produto = _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (img["item_id"],)
    )

    if not produto:
        abort(404)

    _execute(
        """
        UPDATE itens
        SET imagem = %s
        WHERE id = %s
        """,
        (img["arquivo"], produto["id"])
    )

    flash("Imagem definida como principal.", "success")
    return redirect(url_for("admin.editar_produto", id=produto["id"]))


@admin.route("/produto/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_produto(id):
    produto = _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (id,)
    )

    if not produto:
        abort(404)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        existe_em_pedido = _fetch_one(
            """
            SELECT id
            FROM itens_pedido
            WHERE item_id = %s
            LIMIT 1
            """,
            (id,)
        )

        if existe_em_pedido:
            cur.execute(
                """
                UPDATE itens
                SET ativo = FALSE
                WHERE id = %s
                """,
                (id,)
            )
            conn.commit()
            flash("Produto desativado com sucesso! Ele não foi apagado porque já existe em pedidos.", "warning")
            return redirect(url_for("admin.produtos"))

        imagens_extras = _fetch_all(
            """
            SELECT *
            FROM itens_imagens
            WHERE item_id = %s
            """,
            (id,)
        )

        if produto.get("imagem"):
            _delete_file_if_exists(produto["imagem"])

        for img in imagens_extras:
            if img.get("arquivo"):
                _delete_file_if_exists(img["arquivo"])

        cur.execute(
            """
            DELETE FROM itens_imagens
            WHERE item_id = %s
            """,
            (id,)
        )

        cur.execute(
            """
            DELETE FROM itens
            WHERE id = %s
            """,
            (id,)
        )

        conn.commit()
        flash("Produto excluído com sucesso!", "info")

    except Exception as e:
        conn.rollback()
        print("ERRO AO EXCLUIR PRODUTO:", e)
        flash("Erro ao excluir produto.", "danger")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin.produtos"))


# =========================
# USUÁRIOS
# =========================
@admin.route("/usuarios")
@login_required
@admin_required
def usuarios():
    usuarios = _fetch_all(
        """
        SELECT *
        FROM users
        ORDER BY data_criacao DESC
        """
    )
    total_admins = _fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE is_admin = TRUE
        """
    )["total"]

    return render_template("admin/usuarios.html", usuarios=usuarios, total_admins=total_admins)


@admin.route("/usuarios/toggle-admin/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    user = _fetch_one(
        """
        SELECT *
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    if not user:
        abort(404)

    if user["id"] == current_user.id:
        flash("Você não pode alterar seu próprio status de admin.", "warning")
        return redirect(url_for("admin.usuarios"))

    if user["is_admin"]:
        total_admins = _fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM users
            WHERE is_admin = TRUE
            """
        )["total"]

        if total_admins <= 1:
            flash("Você não pode remover o último admin do sistema.", "danger")
            return redirect(url_for("admin.usuarios"))

        _execute(
            """
            UPDATE users
            SET is_admin = FALSE,
                role = %s
            WHERE id = %s
            """,
            ("cliente", user_id)
        )
        flash(f'{user["usuario"]} agora NÃO é mais admin.', "info")

    else:
        _execute(
            """
            UPDATE users
            SET is_admin = TRUE,
                role = %s
            WHERE id = %s
            """,
            ("admin", user_id)
        )
        flash(f'{user["usuario"]} agora é ADMIN ✅', "success")

    return redirect(url_for("admin.usuarios"))


# =========================
# PEDIDOS
# =========================
@admin.route("/pedidos")
@login_required
@admin_required
def pedidos():
    pedidos = _fetch_all(
        """
        SELECT p.*, u.usuario, u.email
        FROM pedidos p
        LEFT JOIN users u ON u.id = p.usuario_id
        ORDER BY p.data_criacao DESC
        """
    )
    return render_template("admin/pedidos.html", pedidos=pedidos)


@admin.route("/pedidos/<int:pedido_id>")
@login_required
@admin_required
def pedido_detalhe(pedido_id):
    pedido = _fetch_one(
        """
        SELECT p.*, u.usuario, u.email
        FROM pedidos p
        LEFT JOIN users u ON u.id = p.usuario_id
        WHERE p.id = %s
        """,
        (pedido_id,)
    )

    if not pedido:
        abort(404)

    itens = _fetch_all(
        """
        SELECT *
        FROM itens_pedido
        WHERE pedido_id = %s
        ORDER BY id ASC
        """,
        (pedido_id,)
    )

    return render_template("admin/pedido_detalhe.html", pedido=pedido, itens=itens)


@admin.route("/pedidos/<int:pedido_id>/atualizar", methods=["POST"])
@login_required
@admin_required
def pedido_atualizar(pedido_id):
    pedido = _fetch_one(
        """
        SELECT *
        FROM pedidos
        WHERE id = %s
        """,
        (pedido_id,)
    )

    if not pedido:
        abort(404)

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
        return redirect(url_for("admin.pedido_detalhe", pedido_id=pedido_id))

    _execute(
        """
        UPDATE pedidos
        SET status = %s,
            codigo_rastreamento = %s
        WHERE id = %s
        """,
        (status, rastreio if rastreio else None, pedido_id)
    )

    flash("Pedido atualizado com sucesso!", "success")
    return redirect(url_for("admin.pedido_detalhe", pedido_id=pedido_id))


@admin.route("/produto/toggle/<int:id>", methods=["POST"])
@login_required
@admin_required
def toggle_produto(id):
    produto = _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (id,)
    )

    if not produto:
        abort(404)

    novo_status = not produto["ativo"]

    _execute(
        """
        UPDATE itens
        SET ativo = %s
        WHERE id = %s
        """,
        (novo_status, id)
    )

    if novo_status:
        flash("Produto reativado com sucesso!", "success")
    else:
        flash("Produto desativado com sucesso!", "warning")

    return redirect(url_for("admin.produtos"))