import os
from decimal import Decimal, ROUND_HALF_UP

import stripe
from flask import (
    render_template, redirect, url_for, flash, request, jsonify, abort, session
)
from flask_login import login_user, logout_user, login_required, current_user

from paprica import app, db, oauth
from paprica.models import Item, User, ItemCarrinho, Pedido, ItemPedido, Favorito, Endereco, Categoria, Marca, Banner
from paprica.forms import CadastroForm, LoginForm, EnderecoForm
from authlib.integrations.base_client.errors import OAuthError
import uuid




# =========================================================
# CONFIG STRIPE
# =========================================================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# =========================================================
# HELPERS
# =========================================================
def _dec(v) -> Decimal:
    return Decimal(str(v or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(v) -> int:
    return int(_dec(v) * 100)


def _carrinho_itens_usuario():
    return ItemCarrinho.query.filter_by(usuario_id=current_user.id).all()


def _carrinho_total_reais(itens_carrinho) -> Decimal:
    total = Decimal("0.00")
    for c in itens_carrinho:
        total += _dec(c.item.preco) * int(c.quantidade)
    return total


def _carrinho_resumo_reais():
    itens = _carrinho_itens_usuario()

    total = Decimal("0.00")
    qtd = 0
    lista = []

    for c in itens:
        preco = _dec(c.item.preco)
        quantidade = int(c.quantidade)
        subtotal = preco * quantidade

        total += subtotal
        qtd += quantidade

        lista.append({
            "cart_id": c.id,
            "item_id": c.item.id,
            "nome": c.item.nome,
            "imagem": c.item.imagem,
            "preco": float(preco),
            "quantidade": quantidade,
            "subtotal": float(subtotal),
        })

    return {"qtd": qtd, "total": float(total), "itens": lista}


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

    itens = ItemCarrinho.query.filter_by(usuario_id=current_user.id).all()

    total = Decimal("0.00")
    qtd = 0

    for c in itens:
        total += _dec(c.item.preco) * int(c.quantidade)
        qtd += int(c.quantidade)

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
    banners = Banner.query.filter_by(ativo=True).order_by(Banner.ordem.asc(), Banner.id.desc()).all()

    produtos = Item.query.filter_by(ativo=True).order_by(Item.data_criacao.desc()).limit(10).all()

    categorias = Categoria.query.order_by(Categoria.nome.asc()).limit(10).all()
    marcas = Marca.query.order_by(Marca.nome.asc()).all()

    produtos_essential = (
        Item.query.join(Marca)
        .filter(Item.ativo == True, Marca.nome == "Essential Nutrition")
        .order_by(Item.data_criacao.desc())
        .limit(8)
        .all()
    )

    produtos_vitafor = (
        Item.query.join(Marca)
        .filter(Item.ativo == True, Marca.nome == "Vitafor")
        .order_by(Item.data_criacao.desc())
        .limit(8)
        .all()
    )

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

    query = Item.query.filter_by(ativo=True)

    if termo:
        query = query.filter(
            db.or_(
                Item.nome.ilike(f"%{termo}%"),
                Item.descricao.ilike(f"%{termo}%"),
                Item.cod_barra.ilike(f"%{termo}%")
            )
        )

    if preco_min:
        try:
            query = query.filter(Item.preco >= float(preco_min))
        except ValueError:
            pass

    if preco_max:
        try:
            query = query.filter(Item.preco <= float(preco_max))
        except ValueError:
            pass

    if em_estoque == "1":
        query = query.filter(Item.estoque > 0)

    if categoria_id:
        try:
            query = query.filter(Item.categoria_id == int(categoria_id))
        except ValueError:
            pass

    if marca_id:
        try:
            query = query.filter(Item.marca_id == int(marca_id))
        except ValueError:
            pass

    if ordenar == "menor_preco":
        query = query.order_by(Item.preco.asc())
    elif ordenar == "maior_preco":
        query = query.order_by(Item.preco.desc())
    elif ordenar == "nome_az":
        query = query.order_by(Item.nome.asc())
    else:
        query = query.order_by(Item.data_criacao.desc())

    itens = query.all()
    categorias = Categoria.query.order_by(Categoria.nome.asc()).all()
    marcas = Marca.query.order_by(Marca.nome.asc()).all()

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
        usuario = User.query.filter_by(usuario=form.usuario.data).first()

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
        usuario = User(usuario=form.usuario.data, email=form.email.data)
        usuario.set_senha(form.senha1.data)

        db.session.add(usuario)
        db.session.commit()

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
    pedidos = Pedido.query.filter_by(
        usuario_id=current_user.id
    ).order_by(Pedido.data_criacao.desc()).all()

    itens_comprados = (
        ItemPedido.query
        .join(Pedido, ItemPedido.pedido_id == Pedido.id)
        .filter(Pedido.usuario_id == current_user.id)
        .order_by(ItemPedido.id.desc())
        .all()
    )

    return render_template("perfil.html", pedidos=pedidos, itens=itens_comprados)


# =========================================================
# ENDEREÇOS
# =========================================================
@app.route("/endereco/novo", methods=["GET", "POST"])
@login_required
def novo_endereco():
    form = EnderecoForm()

    if form.validate_on_submit():
        if form.principal.data:
            Endereco.query.filter_by(usuario_id=current_user.id).update({"principal": False})

        endereco = Endereco(
            usuario_id=current_user.id,
            cep=form.cep.data,
            rua=form.rua.data,
            numero=form.numero.data,
            complemento=form.complemento.data,
            bairro=form.bairro.data,
            cidade=form.cidade.data,
            estado=form.estado.data,
            principal=form.principal.data
        )

        db.session.add(endereco)
        db.session.commit()

        flash("Endereço salvo com sucesso!", "success")
        return redirect(url_for("page_perfil"))

    return render_template("endereco_form.html", form=form)


@app.route("/endereco/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_endereco(id):
    endereco = Endereco.query.get_or_404(id)

    if endereco.usuario_id != current_user.id:
        abort(403)

    form = EnderecoForm(obj=endereco)

    if form.validate_on_submit():
        if form.principal.data:
            Endereco.query.filter_by(usuario_id=current_user.id).update({"principal": False})

        form.populate_obj(endereco)
        db.session.commit()

        flash("Endereço atualizado com sucesso!", "success")
        return redirect(url_for("page_perfil"))

    return render_template("endereco_form.html", form=form)


@app.route("/endereco/principal/<int:id>", methods=["POST"])
@login_required
def definir_endereco_principal(id):
    endereco = Endereco.query.get_or_404(id)

    if endereco.usuario_id != current_user.id:
        abort(403)

    Endereco.query.filter_by(usuario_id=current_user.id).update({"principal": False})
    endereco.principal = True
    db.session.commit()

    flash("Endereço principal atualizado!", "success")
    return redirect(url_for("page_perfil"))


@app.route("/endereco/excluir/<int:id>", methods=["POST"])
@login_required
def excluir_endereco(id):
    endereco = Endereco.query.get_or_404(id)

    if endereco.usuario_id != current_user.id:
        abort(403)

    db.session.delete(endereco)
    db.session.commit()

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
    produto = Item.query.get_or_404(item_id)

    cart_item = ItemCarrinho.query.filter_by(
        usuario_id=current_user.id,
        item_id=produto.id
    ).first()

    if cart_item:
        cart_item.quantidade += 1
    else:
        cart_item = ItemCarrinho(usuario_id=current_user.id, item_id=produto.id, quantidade=1)
        db.session.add(cart_item)

    db.session.commit()
    return jsonify({"success": True, **_carrinho_resumo_reais()})


@app.route("/api/carrinho/atualizar/<int:cart_id>", methods=["POST"])
@login_required
def api_atualizar_carrinho(cart_id):
    data = request.get_json(silent=True) or {}
    quantidade = int(data.get("quantidade", 1))

    cart_item = ItemCarrinho.query.filter_by(
        id=cart_id,
        usuario_id=current_user.id
    ).first_or_404()

    if quantidade <= 0:
        db.session.delete(cart_item)
    else:
        cart_item.quantidade = quantidade

    db.session.commit()
    return jsonify({"success": True, **_carrinho_resumo_reais()})


@app.route("/api/carrinho/remover/<int:cart_id>", methods=["POST"])
@login_required
def api_remover_carrinho(cart_id):
    cart_item = ItemCarrinho.query.filter_by(
        id=cart_id,
        usuario_id=current_user.id
    ).first_or_404()

    db.session.delete(cart_item)
    db.session.commit()

    return jsonify({"success": True, **_carrinho_resumo_reais()})


# =========================================================
# FAVORITOS
# =========================================================
@app.route("/favoritar/<int:item_id>")
@login_required
def favoritar(item_id):
    ja_existe = Favorito.query.filter_by(usuario_id=current_user.id, item_id=item_id).first()

    if not ja_existe:
        db.session.add(Favorito(usuario_id=current_user.id, item_id=item_id))
        db.session.commit()

    return redirect(url_for("meus_favoritos"))


@app.route("/meus-favoritos")
@login_required
def meus_favoritos():
    favoritos = Favorito.query.filter_by(usuario_id=current_user.id).all()
    return render_template("meus_favoritos.html", favoritos=favoritos)


@app.route("/remover-favorito/<int:item_id>")
@login_required
def remover_favorito(item_id):
    favorito = Favorito.query.filter_by(usuario_id=current_user.id, item_id=item_id).first()

    if favorito:
        db.session.delete(favorito)
        db.session.commit()

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

    endereco_principal = Endereco.query.filter_by(
        usuario_id=current_user.id,
        principal=True
    ).first()

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

    endereco = Endereco.query.filter_by(usuario_id=current_user.id, principal=True).first()
    if not endereco:
        flash("Cadastre um endereço principal antes de finalizar.", "warning")
        return redirect(url_for("page_perfil"))

    total_produtos = _carrinho_total_reais(itens)
    frete_valor = _dec(frete["valor"])
    total_final = (total_produtos + frete_valor).quantize(Decimal("0.01"))

    # cria pedido no banco ANTES do pagamento
    pedido = Pedido(
        usuario_id=current_user.id,
        total_produtos=total_produtos,
        frete_valor=frete_valor,
        total_final=total_final,
        status="aguardando_pagamento",
        gateway="stripe",
        status_pagamento="pending",
        frete_nome=frete["nome"],
        frete_prazo=int(frete["prazo"]),
        cep=endereco.cep,
        rua=endereco.rua,
        numero=endereco.numero,
        complemento=endereco.complemento,
        bairro=endereco.bairro,
        cidade=endereco.cidade,
        estado=endereco.estado
    )
    db.session.add(pedido)
    db.session.flush()

    for c in itens:
        db.session.add(ItemPedido(
            pedido_id=pedido.id,
            item_id=c.item.id,
            nome_produto=c.item.nome,
            quantidade=int(c.quantidade),
            preco_unitario=_dec(c.item.preco)
        ))

    db.session.commit()

    try:
        session_checkout = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(pedido.id),
            success_url=url_for("stripe_sucesso", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("stripe_cancelado", pedido_id=pedido.id, _external=True),
            customer_email=current_user.email,
            metadata={
                "pedido_id": str(pedido.id),
                "usuario_id": str(current_user.id),
            },
            line_items=[
                {
                    "price_data": {
                        "currency": "brl",
                        "product_data": {
                            "name": f"Pedido #{pedido.id} - {len(itens)} item(ns)"
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

        pedido.transacao_id = session_checkout.id
        db.session.commit()

        return redirect(session_checkout.url, code=303)

    except Exception as e:
        pedido.status_pagamento = "error"
        db.session.commit()
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
            pedido = Pedido.query.get(int(pedido_id))
            if pedido and checkout_session.payment_status == "paid":
                pedido.status = "pago"
                pedido.status_pagamento = "paid"
                pedido.transacao_id = checkout_session.payment_intent or checkout_session.id

                # limpa carrinho do usuário
                ItemCarrinho.query.filter_by(usuario_id=current_user.id).delete()
                db.session.commit()
                _frete_session_clear()

        flash("Pagamento aprovado com sucesso!", "success")
    except Exception:
        flash("Pagamento concluído. A confirmação final será feita em instantes.", "info")

    return redirect(url_for("page_perfil"))


@app.route("/stripe/cancelado/<int:pedido_id>")
@login_required
def stripe_cancelado(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    if pedido.usuario_id != current_user.id:
        abort(403)

    pedido.status = "aguardando_pagamento"
    pedido.status_pagamento = "canceled"
    db.session.commit()

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
            pedido = Pedido.query.get(int(pedido_id))
            if pedido:
                pedido.status = "pago"
                pedido.status_pagamento = "paid"
                pedido.transacao_id = session_obj.get("payment_intent") or session_obj.get("id")

                # limpa carrinho do usuário dono do pedido
                ItemCarrinho.query.filter_by(usuario_id=pedido.usuario_id).delete()
                db.session.commit()

    elif event["type"] == "checkout.session.expired":
        session_obj = event["data"]["object"]
        pedido_id = None

        if session_obj.get("metadata"):
            pedido_id = session_obj["metadata"].get("pedido_id")

        if pedido_id:
            pedido = Pedido.query.get(int(pedido_id))
            if pedido:
                pedido.status_pagamento = "expired"
                db.session.commit()

    return "ok", 200

# =========================================================
# PRODUTO DETALHE
# =========================================================
@app.route("/produto/<int:item_id>")
def produto_detalhe(item_id):
    item = Item.query.filter_by(id=item_id, ativo=True).first_or_404()

    relacionados_query = Item.query.filter(
        Item.ativo == True,
        Item.id != item.id
    )

    if item.categoria_id:
        relacionados_query = relacionados_query.filter(
            Item.categoria_id == item.categoria_id
        )
    elif item.marca_id:
        relacionados_query = relacionados_query.filter(
            Item.marca_id == item.marca_id
        )

    relacionados = (
        relacionados_query
        .order_by(Item.data_criacao.desc())
        .limit(8)
        .all()
    )

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
            flash(
                "Não foi possível obter os dados da conta Google.",
                "danger"
            )
            return redirect(url_for("page_login"))

        usuario = User.query.filter(
            db.or_(
                User.google_id == google_id,
                User.email == email
            )
        ).first()

        # =========================
        # USUÁRIO JÁ EXISTE
        # =========================
        if usuario:

            if not usuario.google_id:
                usuario.google_id = google_id

            if not usuario.avatar:
                usuario.avatar = avatar

        # =========================
        # NOVO USUÁRIO
        # =========================
        else:

            base_username = "".join(
                ch for ch in nome.lower().replace(" ", "_")
                if ch.isalnum() or ch == "_"
            ) or email.split("@")[0]

            username_final = base_username
            contador = 1

            while User.query.filter_by(
                usuario=username_final
            ).first():

                username_final = f"{base_username}_{contador}"
                contador += 1

            usuario = User(
                usuario=username_final,
                email=email,
                google_id=google_id,
                avatar=avatar,
                role="cliente",
                is_admin=False
            )

            # senha aleatória (exigência do banco)
            usuario.set_senha(uuid.uuid4().hex)

            db.session.add(usuario)

        db.session.commit()

        login_user(usuario)

        flash(
            "Login com Google realizado com sucesso!",
            "success"
        )

        if usuario.is_admin:
            return redirect(url_for("admin.dashboard"))

        return redirect(url_for("page_produto"))

    except OAuthError as e:

        flash(
            f"Erro OAuth Google: {str(e)}",
            "danger"
        )

        return redirect(url_for("page_login"))

    except Exception as e:

        flash(
            f"Erro geral Google Login: {str(e)}",
            "danger"
        )

        return redirect(url_for("page_login"))
