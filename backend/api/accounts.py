import re
import secrets
from functools import wraps
from hmac import compare_digest

from flask import Blueprint, abort, current_app, g, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import AgentProfile, User
from database.store import get_session

accounts_api = Blueprint("accounts", __name__)


def json_body() -> dict:
    data = request.get_json()
    if not isinstance(data, dict):
        abort(400, description="请提交 JSON 对象")
    return data


def text_field(data: dict, name: str, maximum: int, minimum: int = 1) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        abort(400, description=f"{name} 长度须为 {minimum}–{maximum} 个字符")
    return value.strip()


def login_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not g.user:
            abort(401, description="请先登录")
        return func(*args, **kwargs)

    return wrapped


def owned(model, id):
    row = get_session().scalar(select(model).where(model.id == id, model.user_id == g.user.id))
    if row is None:
        abort(404, description="记录不存在")
    return row


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(24)
    return session["csrf_token"]


def login_user(user) -> dict:
    session.clear()
    session["user_id"] = user.id
    return {"user": user.public(), "csrf_token": csrf_token()}


def init_accounts(app):
    @app.before_request
    def account_context():
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            g.user = get_session().get(User, user_id)
            if g.user is None:
                session.clear()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and (
            request.path.startswith(
                ("/api/auth/", "/api/agents", "/api/conversations", "/api/sources")
            )
            or (g.user and request.path.startswith("/api/digests"))
        ):
            expected = session.get("csrf_token", "")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not compare_digest(expected.encode(), supplied.encode()):
                abort(403, description="页面会话已变化，请刷新后重试")

    app.register_blueprint(accounts_api)


@accounts_api.get("/api/auth/me")
def me():
    return jsonify(user=g.user.public() if g.user else None, csrf_token=csrf_token())


@accounts_api.post("/api/auth/register")
def register():
    data = json_body()
    username = text_field(data, "username", 32, 3).lower()
    if not re.fullmatch(r"[a-z0-9_]+", username):
        abort(400, description="用户名使用 3–32 位英文字母、数字或下划线")
    password = data.get("password")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        abort(400, description="密码长度须为 8–128 个字符")
    db = get_session()
    user = User(username=username, password_hash=generate_password_hash(password))
    db.add(user)
    try:
        db.flush()
        db.add(
            AgentProfile(
                user_id=user.id,
                name="资讯助手",
                provider=current_app.config["SIGHT_PROVIDER"],
                model=current_app.config["SIGHT_MODEL"],
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="用户名已存在")
    return jsonify(login_user(user)), 201


@accounts_api.post("/api/auth/login")
def login():
    data = json_body()
    username = text_field(data, "username", 32, 3).lower()
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 128:
        abort(400, description="请输入有效密码")
    user = get_session().scalar(select(User).where(User.username == username))
    if user is None or not check_password_hash(user.password_hash, password):
        abort(401, description="用户名或密码错误")
    return jsonify(login_user(user))


@accounts_api.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(user=None, csrf_token=csrf_token())
