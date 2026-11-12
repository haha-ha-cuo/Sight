import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from flask import Flask, jsonify

from api.rss import rss_api
from db import get_connection


def create_app() -> Flask:
    load_dotenv(Path(__file__).with_name(".env"))
    provider = os.getenv("SIGHT_PROVIDER", "deepseek").strip().lower()
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=16 * 1024,
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
    app.register_blueprint(rss_api)

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
