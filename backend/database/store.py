"""SQLAlchemy 存储：MySQL 用于开发，SQLite 仅用于隔离测试。"""

import re
import secrets
from pathlib import Path

import click
import pymysql
from flask import current_app, g, jsonify
from sqlalchemy import URL, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.models import Base


def get_session() -> Session:
    if "db_session" not in g:
        g.db_session = Session(current_app.extensions["sight_engine"], expire_on_commit=False)
    return g.db_session


def init_schema(app) -> None:
    if not app.config.get("DATABASE_URL"):
        name = app.config["MYSQL_DATABASE"]
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError("MYSQL_DATABASE 仅支持字母、数字与下划线")
        with (
            pymysql.connect(
                host=app.config["MYSQL_HOST"],
                port=app.config["MYSQL_PORT"],
                user=app.config["MYSQL_USER"],
                password=app.config["MYSQL_PASSWORD"],
                connect_timeout=5,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    Base.metadata.create_all(app.extensions["sight_engine"])


def init_store(app) -> None:
    if not app.secret_key:
        path = Path(app.instance_path) / "session.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x") as file:
                file.write(secrets.token_hex(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
        app.secret_key = path.read_text().strip()
    url = app.config.get("DATABASE_URL") or URL.create(
        "mysql+pymysql",
        username=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        database=app.config["MYSQL_DATABASE"],
        query={"charset": "utf8mb4"},
    )
    options = {"pool_pre_ping": True}
    if str(url).startswith("sqlite"):
        options.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
    else:
        options["connect_args"] = {"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10}
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi_connection, connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    app.extensions["sight_engine"] = engine

    @app.teardown_appcontext
    def close_session(error=None):
        db = g.pop("db_session", None)
        if db is not None:
            db.close()

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db = g.get("db_session")
        if db is not None:
            db.rollback()
        app.logger.warning("Database operation failed")
        return jsonify(
            message="数据库暂不可用，请检查 MySQL 配置并运行 flask --app main init-db"
        ), 503

    @app.cli.command("init-db")
    def init_db_command():
        """创建数据库与原型业务表；不会清空已有数据。"""
        try:
            init_schema(app)
        except (SQLAlchemyError, pymysql.MySQLError, ValueError):
            raise click.ClickException("初始化失败，请检查 MySQL 配置和建库权限") from None
        click.echo("Sight 数据库与业务表已就绪。")
