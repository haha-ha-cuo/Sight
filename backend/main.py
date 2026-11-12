import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from api.accounts import init_accounts
from api.rss import rss_api
from api.workspace import workspace_api
from database.store import init_store
from db import get_connection


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv(Path(__file__).with_name(".env"))
    provider = os.getenv("SIGHT_PROVIDER", "deepseek").strip().lower()
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=64 * 1024,
        SECRET_KEY=os.getenv("SIGHT_SECRET_KEY"),
        DATABASE_URL=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SIGHT_PROVIDER=provider,
        DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        DASHSCOPE_API_KEY=os.getenv("DASHSCOPE_API_KEY", "").strip(),
        SIGHT_MODEL=os.getenv(
            "SIGHT_MODEL", "deepseek-flash" if provider == "deepseek" else "qwen-plus"
        ).strip(),
        MYSQL_HOST=os.getenv("MYSQL_HOST", "127.0.0.1"),
        MYSQL_PORT=int(os.getenv("MYSQL_PORT", "3306")),
        MYSQL_USER=os.getenv("MYSQL_USER", "root"),
        MYSQL_PASSWORD=os.getenv("MYSQL_PASSWORD", ""),
        MYSQL_DATABASE=os.getenv("MYSQL_DATABASE", "sight"),
    )
    if test_config:
        app.config.update(test_config)
    init_store(app)
    init_accounts(app)
    app.register_blueprint(rss_api)
    app.register_blueprint(workspace_api)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(message=error.description), error.code

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", message="Sight 后端运行正常")

    @app.get("/api/health/db")
    def database_health():
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 AS connected")
                    cursor.fetchone()
        except pymysql.MySQLError:
            app.logger.warning("MySQL health check failed")
            return jsonify(status="error", message="MySQL 连接失败，请检查服务和配置"), 503
        return jsonify(status="ok", message="MySQL 连接正常")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
