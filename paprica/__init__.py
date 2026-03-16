from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    FloatField,
    IntegerField,
    TextAreaField,
    FileField,
    BooleanField,
    DecimalField,
    SelectField
)
from wtforms.validators import (
    Length,
    EqualTo,
    Email,
    DataRequired,
    ValidationError,
    NumberRange,
    Optional
)
from flask_wtf.file import FileAllowed
from wtforms.fields import MultipleFileField

from paprica.models import User


class CadastroForm(FlaskForm):
    usuario = StringField(
        label="Username:",
        validators=[Length(min=2, max=30), DataRequired()]
    )

    email = StringField(
        label="E-mail:",
        validators=[Email(), DataRequired()]
    )

    senha1 = PasswordField(
        label="Senha:",
        validators=[Length(min=6), DataRequired()]
    )

    senha2 = PasswordField(
        label="Confirmação de Senha:",
        validators=[EqualTo("senha1"), DataRequired()]
    )

    submit = SubmitField(label="Cadastrar")

    def validate_usuario(self, campo):
        user = User.get_by_usuario(campo.data.strip())
        if user:
            raise ValidationError("Usuário já existe! Escolha outro nome.")

    def validate_email(self, campo):
        email = User.get_by_email(campo.data.strip())
        if email:
            raise ValidationError("E-mail já cadastrado!")


class LoginForm(FlaskForm):
    usuario = StringField(
        label="Username:",
        validators=[DataRequired()]
    )

    senha = PasswordField(
        label="Senha:",
        validators=[DataRequired()]
    )

    submit = SubmitField(label="Entrar")


class ProdutoForm(FlaskForm):
    nome = StringField(
        "Nome",
        validators=[DataRequired()]
    )

    preco = DecimalField(
        "Preço (R$)",
        places=2,
        validators=[DataRequired(), NumberRange(min=0)]
    )

    cod_barra = StringField(
        "Código de Barras",
        validators=[Optional(), Length(max=50)]
    )

    categoria_id = SelectField(
        "Categoria",
        coerce=int,
        validators=[Optional()]
    )

    marca_id = SelectField(
        "Marca",
        coerce=int,
        validators=[Optional()]
    )

    descricao = TextAreaField(
        "Descrição",
        validators=[DataRequired()]
    )

    estoque = IntegerField(
        "Estoque",
        validators=[DataRequired(), NumberRange(min=0)]
    )

    imagem = FileField(
        "Imagem principal",
        validators=[
            Optional(),
            FileAllowed(["jpg", "png", "jpeg", "webp"], "Apenas imagens!")
        ]
    )

    imagens = MultipleFileField(
        "Imagens adicionais (galeria)",
        validators=[
            Optional(),
            FileAllowed(["jpg", "png", "jpeg", "webp"], "Apenas imagens!")
        ]
    )

    peso = FloatField(
        "Peso (kg)",
        validators=[DataRequired(), NumberRange(min=0)]
    )

    altura = FloatField(
        "Altura (cm)",
        validators=[DataRequired(), NumberRange(min=0)]
    )

    largura = FloatField(
        "Largura (cm)",
        validators=[DataRequired(), NumberRange(min=0)]
    )

    comprimento = FloatField(
        "Comprimento (cm)",
        validators=[DataRequired(), NumberRange(min=0)]
    )

    submit = SubmitField("Salvar")


class EnderecoForm(FlaskForm):
    cep = StringField(
        "CEP",
        validators=[DataRequired(), Length(min=8, max=9)]
    )

    rua = StringField(
        "Rua",
        validators=[DataRequired()]
    )

    numero = StringField(
        "Número",
        validators=[DataRequired()]
    )

    complemento = StringField("Complemento")

    bairro = StringField(
        "Bairro",
        validators=[DataRequired()]
    )

    cidade = StringField(
        "Cidade",
        validators=[DataRequired()]
    )

    estado = StringField(
        "Estado",
        validators=[DataRequired(), Length(min=2, max=2)]
    )

    principal = BooleanField("Definir como endereço principal")

    submit = SubmitField("Salvar Endereço")

    def validate_cep(self, campo):
        campo.data = (campo.data or "").replace("-", "").strip()


class MarcaForm(FlaskForm):
    nome = StringField(
        "Nome da Marca",
        validators=[DataRequired(), Length(max=100)]
    )

    logo = FileField(
        "Logo da marca",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Apenas imagens!")
        ]
    )

    submit = SubmitField("Salvar Marca")


class CategoriaForm(FlaskForm):
    nome = StringField(
        "Nome da Categoria",
        validators=[DataRequired(), Length(max=100)]
    )

    imagem = FileField(
        "Imagem da categoria",
        validators=[
            Optional(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Apenas imagens!")
        ]
    )

    submit = SubmitField("Salvar Categoria")


class BannerForm(FlaskForm):
    titulo = StringField(
        "Título",
        validators=[DataRequired(), Length(max=150)]
    )

    imagem = FileField(
        "Imagem do banner",
        validators=[
            DataRequired(),
            FileAllowed(["jpg", "jpeg", "png", "webp"], "Apenas imagens!")
        ]
    )

    link = StringField(
        "Link do banner",
        validators=[Optional(), Length(max=300)]
    )

    ordem = IntegerField(
        "Ordem",
        validators=[Optional()]
    )

    ativo = BooleanField(
        "Banner ativo",
        default=True
    )

    submit = SubmitField("Salvar Banner")