"""从项目根目录运行：uv run --project backend python scripts/init_db.py。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database.models import Base  # noqa: E402
from database.store import init_schema  # noqa: E402
from main import create_app  # noqa: E402


def main() -> int:
    app = create_app()
    try:
        init_schema(app)
    except Exception:
        print("初始化失败：请检查 backend/.env 中的 MySQL 连接配置与建库权限。", file=sys.stderr)
        return 1
    print(f"Sight 数据库已就绪，共 {len(Base.metadata.tables)} 张业务表；已有数据保留。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
