import os
import uuid
from decimal import Decimal, ROUND_HALF_UP

import stripe
from flask import (
    render_template, redirect, url_for, flash, request, jsonify, abort, session
)
from flask_login import login_user, logout_user, login_required, current_user
from authlib.integrations.base_client.errors import OAuthError

from paprica import app, oauth, get_db_connection
from paprica.models import User
from paprica.forms import CadastroForm, LoginForm, EnderecoForm


# =========================================================
# CONFIG STRIPE
# =========================================================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# =========================================================
# HELPERS GERAIS
# =========================================================
def _dec(v) -> Decimal:
    return Decimal(str(v or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(v) -> int:
    return int(_dec(v) * 100)


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


def _execute(query, params=None, commit=True, returning=False):
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


def _slugify_username(value: str) -> str:
    base = "".join(
        ch for ch in value.lower().replace(" ", "_")
        if ch.isalnum() or ch == "_"
    )
    return base or "usuario"


# =========================================================
# HELPERS PRODUTOS / CATEGORIAS / MARCAS / BANNERS
# =========================================================
def _get_banners_ativos():
    return _fetch_all(
        """
        SELECT id, titulo, imagem, link, ativo, ordem, data_criacao
        FROM banners
        WHERE ativo = TRUE
        ORDER BY ordem ASC, id DESC
        """
    )


def _get_produtos_recentes(limit=10):
    return _fetch_all(
        """
        SELECT *
        FROM itens
        WHERE ativo = TRUE
        ORDER BY data_criacao DESC
        LIMIT %s
        """,
        (limit,)
    )


def _get_categorias(limit=None):
    if limit:
        return _fetch_all(
            """
            SELECT *
            FROM categorias
            ORDER BY nome ASC
            LIMIT %s
            """,
            (limit,)
        )

    return _fetch_all(
        """
        SELECT *
        FROM categorias
        ORDER BY nome ASC
        """
    )


def _get_marcas():
    return _fetch_all(
        """
        SELECT *
        FROM marcas
        ORDER BY nome ASC
        """
    )


def _get_produtos_por_nome_marca(nome_marca, limit=8):
    return _fetch_all(
        """
        SELECT i.*
        FROM itens i
        INNER JOIN marcas m ON m.id = i.marca_id
        WHERE i.ativo = TRUE
          AND m.nome = %s
        ORDER BY i.data_criacao DESC
        LIMIT %s
        """,
        (nome_marca, limit)
    )


def _get_produto_por_id(item_id, apenas_ativo=False):
    if apenas_ativo:
        return _fetch_one(
            """
            SELECT *
            FROM itens
            WHERE id = %s AND ativo = TRUE
            """,
            (item_id,)
        )

    return _fetch_one(
        """
        SELECT *
        FROM itens
        WHERE id = %s
        """,
        (item_id,)
    )


def _buscar_produtos(termo="", preco_min="", preco_max="", em_estoque="", ordenar="recentes", categoria_id="", marca_id=""):
    where = ["i.ativo = TRUE"]
    params = []

    if termo:
        where.append("(i.nome ILIKE %s OR i.descricao ILIKE %s OR i.cod_barra ILIKE %s)")
        like = f"%{termo}%"
        params.extend([like, like, like])

    if preco_min:
        try:
            where.append("i.preco >= %s")
            params.append(float(preco_min))
        except ValueError:
            pass

    if preco_max:
        try:
            where.append("i.preco <= %s")
            params.append(float(preco_max))
        except ValueError:
            pass

    if em_estoque == "1":
        where.append("i.estoque > 0")

    if categoria_id:
        try:
            where.append("i.categoria_id = %s")
            params.append(int(categoria_id))
        except ValueError:
            pass

    if marca_id:
        try:
            where.append("i.marca_id = %s")
            params.append(int(marca_id))
        except ValueError:
            pass

    order_map = {
        "menor_preco": "i.preco ASC",
        "maior_preco": "i.preco DESC",
        "nome_az": "i.nome ASC",
        "recentes": "i.data_criacao DESC"
    }
    order_sql = order_map.get(ordenar, "i.data_criacao DESC")

    query = f"""
        SELECT i.*
        FROM itens i
        WHERE {' AND '.join(where)}
        ORDER BY {order_sql}
    """

    return _fetch_all(query, params)


def _get_relacionados(item, limit=8):
    if not item:
        return []

    where = ["ativo = TRUE", "id <> %s"]
    params = [item["id"]]

    if item.get("categoria_id"):
        where.append("categoria_id = %s")
        params.append(item["categoria_id"])
    elif item.get("marca_id"):
        where.append("marca_id = %s")
        params.append(item["marca_id"])

    query = f"""
        SELECT *
        FROM itens
        WHERE {' AND '.join(where)}
        ORDER BY data_criacao DESC
        LIMIT %s
    """
    params.append(limit)
    return _fetch_all(query, params)


# =========================================================
# HELPERS ENDEREÇOS
# =========================================================
def _get_endereco_por_id(endereco_id):
    return _fetch_one(
        """
        SELECT *
        FROM enderecos
        WHERE id = %s
        """,
        (endereco_id,)
    )


def _get_endereco_principal(usuario_id):
    return _fetch_one(
        """
        SELECT *
        FROM enderecos
        WHERE usuario_id = %s AND principal = TRUE
        ORDER BY id DESC
        LIMIT 1
        """,
        (usuario_id,)
    )


def _get_enderecos_usuario(usuario_id):
    return _fetch_all(
        """
        SELECT *
        FROM enderecos
        WHERE usuario_id = %s
        ORDER BY principal DESC, id DESC
        """,
        (usuario_id,)
    )


# =========================================================
# HELPERS CARRINHO
# =========================================================
def _carrinho_itens_usuario():
    rows = _fetch_all(
        """
        SELECT
            ic.id,
            ic.usuario_id,
            ic.item_id,
            ic.quantidade,
            i.nome,
            i.descricao,
            i.preco,
            i.estoque,
            i.ativo,
            i.imagem,
            i.cod_barra
        FROM itens_carrinho ic
        INNER JOIN itens i ON i.id = ic.item_id
        WHERE ic.usuario_id = %s
        ORDER BY ic.id DESC
        """,
        (current_user.id,)
    )

    itens = []
    for r in rows:
        itens.append({
            "id": r["id"],
            "usuario_id": r["usuario_id"],
            "item_id": r["item_id"],
            "quantidade": r["quantidade"],
            "item": {
                "id": r["item_id"],
                "nome": r["nome"],
                "descricao": r["descricao"],
                "preco": r["preco"],
                "estoque": r["estoque"],
                "ativo": r["ativo"],
                "imagem": r["imagem"],
                "cod_barra": r["cod_barra"],
            }
        })
    return itens


def _get_carrinho_item(cart_id, usuario_id):
    row = _fetch_one(
        """
        SELECT *
        FROM itens_carrinho
        WHERE id = %s AND usuario_id = %s
        """,
        (cart_id, usuario_id)
    )
    return row


def _get_carrinho_item_por_produto(usuario_id, item_id):
    return _fetch_one(
        """
        SELECT *
        FROM itens_carrinho
        WHERE usuario_id = %s AND item_id = %s
        """,
        (usuario_id, item_id)
    )


def _carrinho_total_reais(itens_carrinho) -> Decimal:
    total = Decimal("0.00")
    for c in itens_carrinho:
        total += _dec(c["item"]["preco"]) * int(c["quantidade"])
    return total


def _carrinho_resumo_reais():
    itens = _carrinho_itens_usuario()

    total = Decimal("0.00")
    qtd = 0
    lista = []

    for c in itens:
        preco = _dec(c["item"]["preco"])
        quantidade = int(c["quantidade"])
        subtotal = preco * quantidade

        total += subtotal
        qtd += quantidade

        lista.append({
            "cart_id": c["id"],
            "item_id": c["item"]["id"],
            "nome": c["item"]["nome"],
            "imagem": c["item"]["imagem"],
            "preco": float(preco),
            "quantidade": quantidade,
            "subtotal": float(subtotal),
        })

    return {"qtd": qtd, "total": float(total), "itens": lista}


def _limpar_carrinho_usuario(usuario_id):
    _execute(
        """
        DELETE FROM itens_carrinho
        WHERE usuario_id = %s
        """,
        (usuario_id,)
    )


# =========================================================
# HELPERS PEDIDOS / FAVORITOS
# =========================================================
def _get_pedidos_usuario(usuario_id):
    return _fetch_all(
        """
        SELECT *
        FROM pedidos
        WHERE usuario_id = %s
        ORDER BY data_criacao DESC
        """,
        (usuario_id,)
    )


def _get_pedido_por_id(pedido_id):
    return _fetch_one(
        """
        SELECT *
        FROM pedidos
        WHERE id = %s
        """,
        (pedido_id,)
    )


def _get_itens_comprados_usuario(usuario_id):
    return _fetch_all(
        """
        SELECT
            ip.*,
            p.data_criacao AS pedido_data_criacao,
            p.status AS pedido_status
        FROM itens_pedido ip
        INNER JOIN pedidos p ON p.id = ip.pedido_id
        WHERE p.usuario_id = %s
        ORDER BY ip.id DESC
        """,
        (usuario_id,)
    )


def _get_favoritos_usuario(usuario_id):
    return _fetch_all(
        """
        SELECT
            f.id,
            f.usuario_id,
            f.item_id,
            i.nome,
            i.preco,
            i.imagem,
            i.ativo,
            i.descricao
        FROM favoritos f
        INNER JOIN itens i ON i.id = f.item_id
        WHERE f.usuario_id = %s
        ORDER BY f.id DESC
        """,
        (usuario_id,)
    )


def _favorito_existe(usuario_id, item_id):
    return _fetch_one(
        """
        SELECT id
        FROM favoritos
        WHERE usuario_id = %s AND item_id = %s
        """,
        (usuario_id, item_id)
    )


# =========================================================
# FRETE SESSION
# =========================================================
def _frete_session_get():
    return session.get("frete_escolhido")


def _frete_session_set(payload: dict):
    session["frete_escolhido"] = payload


def _frete_session_clear():
    session.pop("frete_escolhido", None)


# =========================================================
# CONTEXT GLOBAL
# =========================================================
@app.context_processor
def carrinho_global():
    if not current_user.is_authenticated:
        return dict(carrinho_itens=[], carrinho_total=Decimal("0.00"), carrinho_quantidade=0)

    itens = _carrinho_itens_usuario()
    total = Decimal("0.00")
    qtd = 0

    for c in itens:
        total += _dec(c["item"]["preco"]) * int(c["quantidade"])
        qtd += int(c["quantidade"])

    return dict(
        carrinho_itens=itens,
        carrinho_total=total,
        carrinho_quantidade=qtd
    )


# =========================================================
# HOME / PRODUTOS
# =========================================================
@app.route("/")
def page_home():
    banners = _get_banners_ativos()
    produtos = _get_produtos_recentes(10)
    categorias = _get_categorias(10)
    marcas = _get_marcas()

    produtos_essential = _get_produtos_por_nome_marca("Essential Nutrition", 8)
    produtos_vitafor = _get_produtos_por_nome_marca("Vitafor", 8)

    return render_template(
        "home.html",
        banners=banners,
        produtos=produtos,
        categorias=categorias,
        marcas=marcas,
        produtos_essential=produtos_essential,
        produtos_vitafor=produtos_vitafor
    )


@app.route("/produtos")
def page_produto():
    termo = (request.args.get("q") or "").strip()
    preco_min = (request.args.get("preco_min") or "").strip()
    preco_max = (request.args.get("preco_max") or "").strip()
    em_estoque = (request.args.get("em_estoque") or "").strip()
    ordenar = (request.args.get("ordenar") or "recentes").strip()
    categoria_id = (request.args.get("categoria_id") or "").strip()
    marca_id = (request.args.get("marca_id") or "").strip()

    itens = _buscar_produtos(
        termo=termo,
        preco_min=preco_min,
        preco_max=preco_max,
        em_estoque=em_estoque,
        ordenar=ordenar,
        categoria_id=categoria_id,
        marca_id=marca_id
    )

    categorias = _get_categorias()
    marcas = _get_marcas()

    return render_template(
        "produtos.html",
        itens=itens,
        termo_busca=termo,
        categorias=categorias,
        marcas=marcas,
        filtros={
            "preco_min": preco_min,
            "preco_max": preco_max,
            "em_estoque": em_estoque,
            "ordenar": ordenar,
            "categoria_id": categoria_id,
            "marca_id": marca_id
        }
    )


# =========================================================
# LOGIN / LOGOUT / CADASTRO
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def page_login():
    form = LoginForm()

    if form.validate_on_submit():
        usuario = User.get_by_usuario(form.usuario.data)

        if usuario and usuario.check_senha(form.senha.data):
            login_user(usuario)
            flash("Login realizado com sucesso!", "success")

            if usuario.is_admin:
                return redirect(url_for("admin.dashboard"))

            return redirect(url_for("page_produto"))

        flash("Usuário ou senha incorretos", "danger")

    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado", "info")
    return redirect(url_for("page_home"))


@app.route("/cadastro", methods=["GET", "POST"])
def page_cadastro():
    form = CadastroForm()

    if form.validate_on_submit():
        if User.get_by_usuario(form.usuario.data):
            flash("Esse nome de usuário já está em uso.", "danger")
            return render_template("cadastro.html", form=form)

        if User.get_by_email(form.email.data):
            flash("Esse e-mail já está cadastrado.", "danger")
            return render_template("cadastro.html", form=form)

        User.create(
            usuario=form.usuario.data,
            email=form.email.data,
            senha=form.senha1.data,
            role="cliente",
            is_admin=False
        )

        flash("Cadastro realizado com sucesso!", "success")
        return redirect(url_for("page_login"))

    if form.errors:
        for errs in form.errors.values():
            for err in errs:
                flash(err, "danger")

    return render_template("cadastro.html", form=form)


# =========================================================
# PERFIL
# =========================================================
@app.route("/perfil")
@login_required
def page_perfil():
    pedidos = _get_pedidos_usuario(current_user.id)
    itens_comprados = _get_itens_comprados_usuario(current_user.id)
    enderecos = _get_enderecos_usuario(current_user.id)

    return render_template(
        "perfil.html",
        pedidos=pedidos,
        itens=itens_comprados,
        enderecos=enderecos
    )


# =========================================================
# ENDEREÇOS
# =========================================================
@app.route("/endereco/novo", methods=["GET", "POST"])
@login_required
def novo_endereco():
    form = EnderecoForm()

    if form.validate_on_submit():
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if form.principal.data:
                cur.execute(
                    """
                    UPDATE enderecos
                    SET principal = FALSE
                    WHERE usuario_id = %s
                    """,
                    (current_user.id,)
                )

            cur.execute(
                """
                INSERT INTO enderecos (
                    usuario_id, cep, rua, numero, complemento,
                    bairro, cidade, estado, principal
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    current_user.id,
                    form.cep.data,
                    form.rua.data,
                    form.numero.data,
                    form.complemento.data,
                    form.bairro.data,
                    form.cidade.data,
                    form.estado.data,
                    form.principal.data
                )
            )
            conn.commit()
            flash("Endereço salvo com sucesso!", "success")
            return redirect(url_for("page_perfil"))
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    return render_template("endereco_form.html", form=form)


@app.route("/endereco/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_endereco(id):
    endereco = _get_endereco_por_id(id)

    if not endereco:
        abort(404)

    if endereco["usuario_id"] != current_user.id:
        abort(403)

    form = EnderecoForm(data=endereco)

    if form.validate_on_submit():
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if form.principal.data:
                cur.execute(
                    """
                    UPDATE enderecos
                    SET principal = FALSE
                    WHERE usuario_id = %s
                    """,
                    (current_user.id,)
                )

            cur.execute(
                """
                UPDATE enderecos
                SET cep = %s,
                    rua = %s,
                    numero = %s,
                    complemento = %s,
                    bairro = %s,
                    cidade = %s,
                    estado = %s,
                    principal = %s
                WHERE id = %s
                """,
                (
                    form.cep.data,
                    form.rua.data,
                    form.numero.data,
                    form.complemento.data,
                    form.bairro.data,
                    form.cidade.data,
                    form.estado.data,
                    form.principal.data,
                    id
                )
            )
            conn.commit()
            flash("Endereço atualizado com sucesso!", "success")
            return redirect(url_for("page_perfil"))
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    return render_template("endereco_form.html", form=form, endereco=endereco)


@app.route("/endereco/principal/<int:id>", methods=["POST"])
@login_required
def definir_endereco_principal(id):
    endereco = _get_endereco_por_id(id)

    if not endereco:
        abort(404)

    if endereco["usuario_id"] != current_user.id:
        abort(403)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE enderecos
            SET principal = FALSE
            WHERE usuario_id = %s
            """,
            (current_user.id,)
        )
        cur.execute(
            """
            UPDATE enderecos
            SET principal = TRUE
            WHERE id = %s
            """,
            (id,)
        )
        conn.commit()
        flash("Endereço principal atualizado!", "success")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("page_perfil"))


@app.route("/endereco/excluir/<int:id>", methods=["POST"])
@login_required
def excluir_endereco(id):
    endereco = _get_endereco_por_id(id)

    if not endereco:
        abort(404)

    if endereco["usuario_id"] != current_user.id:
        abort(403)

    _execute(
        """
        DELETE FROM enderecos
        WHERE id = %s
        """,
        (id,)
    )

    flash("Endereço excluído!", "info")
    return redirect(url_for("page_perfil"))


# =========================================================
# CARRINHO
# =========================================================
@app.route("/api/carrinho/resumo", methods=["GET"])
@login_required
def api_carrinho_resumo():
    return jsonify({"success": True, **_carrinho_resumo_reais()})


@app.route("/api/carrinho/adicionar/<int:item_id>", methods=["POST"])
@login_required
def api_adicionar_carrinho(item_id):
    produto = _get_produto_por_id(item_id, apenas_ativo=False)

    if not produto:
        abort(404)

    cart_item = _get_carrinho_item_por_produto(current_user.id, produto["id"])

    if cart_item:
        _execute(
            """
            UPDATE itens_carrinho
            SET quantidade = quantidade + 1
            WHERE id = %s
            """,
            (cart_item["id"],)
        )
    else:
        _execute(
            """
            INSERT INTO itens_carrinho (usuario_id, item_id, quantidade)
            VALUES (%s, %s, %s)
            """,
            (current_user.id, produto["id"], 1)
        )

    return jsonify({"success": True, **_carrinho_resumo_reais()})


@app.route("/api/carrinho/atualizar/<int:cart_id>", methods=["POST"])
@login_required
def api_atualizar_carrinho(cart_id):
    data = request.get_json(silent=True) or {}
    quantidade = int(data.get("quantidade", 1))

    cart_item = _get_carrinho_item(cart_id, current_user.id)

    if not cart_item:
        abort(404)

    if quantidade <= 0:
        _execute(
            """
            DELETE FROM itens_carrinho
            WHERE id = %s
            """,
            (cart_id,)
        )
    else:
        _execute(
            """
            UPDATE itens_carrinho
            SET quantidade = %s
            WHERE id = %s
            """,
            (quantidade, cart_id)
        )

    return jsonify({"success": True, **_carrinho_resumo_reais()})


@app.route("/api/carrinho/remover/<int:cart_id>", methods=["POST"])
@login_required
def api_remover_carrinho(cart_id):
    cart_item = _get_carrinho_item(cart_id, current_user.id)

    if not cart_item:
        abort(404)

    _execute(
        """
        DELETE FROM itens_carrinho
        WHERE id = %s
        """,
        (cart_id,)
    )

    return jsonify({"success": True, **_carrinho_resumo_reais()})


# =========================================================
# FAVORITOS
# =========================================================
@app.route("/favoritar/<int:item_id>")
@login_required
def favoritar(item_id):
    produto = _get_produto_por_id(item_id)

    if not produto:
        abort(404)

    ja_existe = _favorito_existe(current_user.id, item_id)

    if not ja_existe:
        _execute(
            """
            INSERT INTO favoritos (usuario_id, item_id)
            VALUES (%s, %s)
            """,
            (current_user.id, item_id)
        )

    return redirect(url_for("meus_favoritos"))


@app.route("/meus-favoritos")
@login_required
def meus_favoritos():
    favoritos = _get_favoritos_usuario(current_user.id)
    return render_template("meus_favoritos.html", favoritos=favoritos)


@app.route("/remover-favorito/<int:item_id>")
@login_required
def remover_favorito(item_id):
    _execute(
        """
        DELETE FROM favoritos
        WHERE usuario_id = %s AND item_id = %s
        """,
        (current_user.id, item_id)
    )

    return redirect(url_for("meus_favoritos"))


# =========================================================
# CHECKOUT / FRETE
# =========================================================
@app.route("/checkout", methods=["GET"])
@login_required
def checkout():
    itens = _carrinho_itens_usuario()
    if not itens:
        flash("Seu carrinho está vazio.", "warning")
        return redirect(url_for("page_produto"))

    total_produtos = _carrinho_total_reais(itens)
    endereco_principal = _get_endereco_principal(current_user.id)

    frete_escolhido = _frete_session_get()
    frete_valor = _dec(frete_escolhido["valor"]) if frete_escolhido else Decimal("0.00")
    total_final = (total_produtos + frete_valor).quantize(Decimal("0.01"))

    return render_template(
        "checkout.html",
        itens=itens,
        total_produtos=total_produtos,
        endereco_principal=endereco_principal,
        frete_escolhido=frete_escolhido,
        frete_valor=frete_valor,
        total_final=total_final,
        stripe_publishable_key=os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    )


@app.route("/api/frete/opcoes", methods=["POST"])
@login_required
def api_frete_opcoes():
    data = request.get_json(silent=True) or {}
    cep = (data.get("cep") or "").replace("-", "").strip()

    if len(cep) != 8:
        return jsonify({"erro": "CEP inválido"}), 400

    carrinho = _carrinho_itens_usuario()
    if not carrinho:
        return jsonify({"erro": "Carrinho vazio"}), 400

    fretes = [
        {"id": "normal", "nome": "Entrega Normal", "valor": "19.90", "prazo": 6, "cep": cep},
        {"id": "expresso", "nome": "Entrega Expressa", "valor": "34.90", "prazo": 3, "cep": cep},
    ]

    return jsonify({"success": True, "fretes": fretes})


@app.route("/api/frete/selecionar", methods=["POST"])
@login_required
def api_frete_selecionar():
    data = request.get_json(silent=True) or {}

    required = ["id", "nome", "valor", "prazo", "cep"]
    for k in required:
        if k not in data:
            return jsonify({"erro": f"Campo ausente: {k}"}), 400

    payload = {
        "id": str(data["id"]),
        "nome": str(data["nome"]),
        "valor": str(_dec(data["valor"])),
        "prazo": int(data["prazo"]),
        "cep": str(data["cep"]).replace("-", "").strip(),
    }

    if len(payload["cep"]) != 8:
        return jsonify({"erro": "CEP inválido"}), 400

    _frete_session_set(payload)
    return jsonify({"success": True, "frete": payload})


@app.route("/api/frete/limpar", methods=["POST"])
@login_required
def api_frete_limpar():
    _frete_session_clear()
    return jsonify({"success": True})


# =========================================================
# PEDIDO + STRIPE CHECKOUT
# =========================================================
@app.route("/checkout/stripe", methods=["POST"])
@login_required
def checkout_stripe():
    if not stripe.api_key:
        flash("Stripe não configurada no servidor.", "danger")
        return redirect(url_for("checkout"))

    itens = _carrinho_itens_usuario()
    if not itens:
        flash("Carrinho vazio.", "warning")
        return redirect(url_for("page_produto"))

    frete = _frete_session_get()
    if not frete:
        flash("Selecione um frete antes de pagar.", "warning")
        return redirect(url_for("checkout"))

    endereco = _get_endereco_principal(current_user.id)
    if not endereco:
        flash("Cadastre um endereço principal antes de finalizar.", "warning")
        return redirect(url_for("page_perfil"))

    total_produtos = _carrinho_total_reais(itens)
    frete_valor = _dec(frete["valor"])
    total_final = (total_produtos + frete_valor).quantize(Decimal("0.01"))

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO pedidos (
                usuario_id, total_produtos, frete_valor, total_final,
                status, gateway, status_pagamento, frete_nome, frete_prazo,
                cep, rua, numero, complemento, bairro, cidade, estado
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                current_user.id,
                total_produtos,
                frete_valor,
                total_final,
                "aguardando_pagamento",
                "stripe",
                "pending",
                frete["nome"],
                int(frete["prazo"]),
                endereco["cep"],
                endereco["rua"],
                endereco["numero"],
                endereco["complemento"],
                endereco["bairro"],
                endereco["cidade"],
                endereco["estado"],
            )
        )
        pedido_row = cur.fetchone()
        pedido_id = pedido_row["id"]

        for c in itens:
            cur.execute(
                """
                INSERT INTO itens_pedido (
                    pedido_id, item_id, nome_produto, quantidade, preco_unitario
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    pedido_id,
                    c["item"]["id"],
                    c["item"]["nome"],
                    int(c["quantidade"]),
                    _dec(c["item"]["preco"])
                )
            )

        conn.commit()

    except Exception:
        conn.rollback()
        cur.close()
        conn.close()
        raise

    finally:
        cur.close()
        conn.close()

    try:
        session_checkout = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(pedido_id),
            success_url=url_for("stripe_sucesso", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("stripe_cancelado", pedido_id=pedido_id, _external=True),
            customer_email=current_user.email,
            metadata={
                "pedido_id": str(pedido_id),
                "usuario_id": str(current_user.id),
            },
            line_items=[
                {
                    "price_data": {
                        "currency": "brl",
                        "product_data": {
                            "name": f"Pedido #{pedido_id} - {len(itens)} item(ns)"
                        },
                        "unit_amount": _to_cents(total_produtos),
                    },
                    "quantity": 1,
                },
                {
                    "price_data": {
                        "currency": "brl",
                        "product_data": {
                            "name": f"Frete - {frete['nome']}"
                        },
                        "unit_amount": _to_cents(frete_valor),
                    },
                    "quantity": 1,
                }
            ]
        )

        _execute(
            """
            UPDATE pedidos
            SET transacao_id = %s
            WHERE id = %s
            """,
            (session_checkout.id, pedido_id)
        )

        return redirect(session_checkout.url, code=303)

    except Exception as e:
        _execute(
            """
            UPDATE pedidos
            SET status_pagamento = %s
            WHERE id = %s
            """,
            ("error", pedido_id)
        )
        flash(f"Erro ao iniciar pagamento Stripe: {e}", "danger")
        return redirect(url_for("checkout"))


@app.route("/stripe/sucesso")
@login_required
def stripe_sucesso():
    session_id = request.args.get("session_id")

    if not session_id or not stripe.api_key:
        flash("Pagamento processado. Aguarde confirmação.", "info")
        return redirect(url_for("page_perfil"))

    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        pedido_id = checkout_session.metadata.get("pedido_id") if checkout_session.metadata else None

        if pedido_id:
            pedido = _get_pedido_por_id(int(pedido_id))
            if pedido and checkout_session.payment_status == "paid":
                _execute(
                    """
                    UPDATE pedidos
                    SET status = %s,
                        status_pagamento = %s,
                        transacao_id = %s
                    WHERE id = %s
                    """,
                    (
                        "pago",
                        "paid",
                        checkout_session.payment_intent or checkout_session.id,
                        int(pedido_id)
                    )
                )

                _limpar_carrinho_usuario(current_user.id)
                _frete_session_clear()

        flash("Pagamento aprovado com sucesso!", "success")
    except Exception:
        flash("Pagamento concluído. A confirmação final será feita em instantes.", "info")

    return redirect(url_for("page_perfil"))


@app.route("/stripe/cancelado/<int:pedido_id>")
@login_required
def stripe_cancelado(pedido_id):
    pedido = _get_pedido_por_id(pedido_id)

    if not pedido:
        abort(404)

    if pedido["usuario_id"] != current_user.id:
        abort(403)

    _execute(
        """
        UPDATE pedidos
        SET status = %s,
            status_pagamento = %s
        WHERE id = %s
        """,
        ("aguardando_pagamento", "canceled", pedido_id)
    )

    flash("Pagamento cancelado.", "warning")
    return redirect(url_for("checkout"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    if not stripe.api_key or not STRIPE_WEBHOOK_SECRET:
        return "Stripe webhook não configurado", 500

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return "Payload inválido", 400
    except stripe.error.SignatureVerificationError:
        return "Assinatura inválida", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        pedido_id = None

        if session_obj.get("metadata"):
            pedido_id = session_obj["metadata"].get("pedido_id")

        if pedido_id:
            pedido = _get_pedido_por_id(int(pedido_id))
            if pedido:
                _execute(
                    """
                    UPDATE pedidos
                    SET status = %s,
                        status_pagamento = %s,
                        transacao_id = %s
                    WHERE id = %s
                    """,
                    (
                        "pago",
                        "paid",
                        session_obj.get("payment_intent") or session_obj.get("id"),
                        int(pedido_id)
                    )
                )
                _limpar_carrinho_usuario(pedido["usuario_id"])

    elif event["type"] == "checkout.session.expired":
        session_obj = event["data"]["object"]
        pedido_id = None

        if session_obj.get("metadata"):
            pedido_id = session_obj["metadata"].get("pedido_id")

        if pedido_id:
            pedido = _get_pedido_por_id(int(pedido_id))
            if pedido:
                _execute(
                    """
                    UPDATE pedidos
                    SET status_pagamento = %s
                    WHERE id = %s
                    """,
                    ("expired", int(pedido_id))
                )

    return "ok", 200


# =========================================================
# PRODUTO DETALHE
# =========================================================
@app.route("/produto/<int:item_id>")
def produto_detalhe(item_id):
    item = _get_produto_por_id(item_id, apenas_ativo=True)

    if not item:
        abort(404)

    relacionados = _get_relacionados(item, 8)

    return render_template(
        "produto_detalhe.html",
        item=item,
        relacionados=relacionados
    )


# =========================================================
# LOGIN GOOGLE
# =========================================================
@app.route("/login/google")
def login_google():
    redirect_uri = url_for("login_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/login/google/callback")
def login_google_callback():
    try:
        token = oauth.google.authorize_access_token()

        user_info = token.get("userinfo")

        if not user_info:
            resp = oauth.google.get(
                "https://openidconnect.googleapis.com/v1/userinfo"
            )
            user_info = resp.json()

        google_id = user_info.get("sub")
        email = user_info.get("email")
        nome = user_info.get("name") or email.split("@")[0]
        avatar = user_info.get("picture")

        if not google_id or not email:
            flash("Não foi possível obter os dados da conta Google.", "danger")
            return redirect(url_for("page_login"))

        usuario = User.get_by_google_id(google_id)

        if not usuario:
            usuario = User.get_by_email(email)

        # =========================
        # USUÁRIO JÁ EXISTE
        # =========================
        if usuario:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                if not usuario.google_id:
                    cur.execute(
                        """
                        UPDATE users
                        SET google_id = %s
                        WHERE id = %s
                        """,
                        (google_id, usuario.id)
                    )
                    usuario.google_id = google_id

                if not usuario.avatar and avatar:
                    cur.execute(
                        """
                        UPDATE users
                        SET avatar = %s
                        WHERE id = %s
                        """,
                        (avatar, usuario.id)
                    )
                    usuario.avatar = avatar

                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
                conn.close()

        # =========================
        # NOVO USUÁRIO
        # =========================
        else:
            base_username = _slugify_username(nome)
            username_final = base_username
            contador = 1

            while User.get_by_usuario(username_final):
                username_final = f"{base_username}_{contador}"
                contador += 1

            usuario = User.create(
                usuario=username_final,
                email=email,
                google_id=google_id,
                avatar=avatar,
                senha=uuid.uuid4().hex,
                role="cliente",
                is_admin=False
            )

        login_user(usuario)

        flash("Login com Google realizado com sucesso!", "success")

        if usuario.is_admin:
            return redirect(url_for("admin.dashboard"))

        return redirect(url_for("page_produto"))

    except OAuthError as e:
        flash(f"Erro OAuth Google: {str(e)}", "danger")
        return redirect(url_for("page_login"))

    except Exception as e:
        flash(f"Erro geral Google Login: {str(e)}", "danger")
        return redirect(url_for("page_login"))