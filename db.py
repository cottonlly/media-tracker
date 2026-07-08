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


def init_db():
    """按 schema.sql 建表。表已存在则跳过,可安全重复调用。"""
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
