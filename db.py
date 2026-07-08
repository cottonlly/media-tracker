"""数据库辅助模块。

只用 Python 自带的 sqlite3,不引入 ORM,保持 v1 简单易懂。
以后要换成 SQLAlchemy 等 ORM,也只需改动这一个文件。
"""

import sqlite3
from pathlib import Path

from flask import g

# 数据库文件和建表脚本都放在项目根目录
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "media.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_db():
    """获取当前请求的数据库连接。

    连接存放在 Flask 的 g 对象上,同一个请求内复用,
    请求结束时由 close_db() 统一关闭。
    """
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        # 让查询结果可以像字典一样按列名访问,例如 row["title"]
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """请求结束时关闭数据库连接(注册到 app.teardown_appcontext)。"""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# 后续版本陆续新增的列:列名 -> 该列的 SQLite 类型。
# 用于给「旧库」补列(见 _migrate)。新建库则直接由 schema.sql 带出这些列。
_ADDED_COLUMNS = {
    "year": "INTEGER",       # v1.3
    "overview": "TEXT",      # v1.3
    "poster_url": "TEXT",    # v1.3
}


def init_db():
    """按 schema.sql 建表,并给旧库补齐后加的列。可安全重复调用(幂等)。"""
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """给已存在的旧表补上后来新增的列,兼容历史数据。

    SQLite 不支持 ADD COLUMN IF NOT EXISTS,所以先用 PRAGMA 查出现有列,
    缺哪个补哪个。新列对老记录默认留空(NULL),不会影响或破坏现有数据。
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(records)")}
    for col, col_type in _ADDED_COLUMNS.items():
        if col not in existing:
            # 列名来自本模块内固定的白名单(非用户输入),拼接安全
            conn.execute(f"ALTER TABLE records ADD COLUMN {col} {col_type}")
