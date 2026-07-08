"""个人观影 / 追番 / 读书记录 —— Flask 应用主文件 (v1.1)。

功能:
  - 首页展示添加表单 + 记录列表
  - 列表支持筛选(类型 / 状态)、排序(添加时间 / 评分 / 标题,正倒序)、
    按标题模糊搜索;条件可叠加,并保存在 URL 查询参数里
  - 新增 / 编辑 / 删除记录
  - 数据存在本地 SQLite 文件 media.db

运行:
  python app.py
然后浏览器打开 http://127.0.0.1:5000
"""

from datetime import date

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from db import close_db, get_db, init_db

# ---------------------------------------------------------------------------
# 下拉选项集中定义在这里,以后要加新类型 / 状态,改这两个列表即可
# ---------------------------------------------------------------------------
CATEGORIES = ["动画", "电影", "剧集", "书", "游戏"]
STATUSES = ["想看", "在看", "看完"]

# 允许的排序方式:URL 参数值 -> 对应的 SQL 排序表达式。
# ORDER BY 不能用参数占位符,只能拼字符串,所以必须用白名单防止 SQL 注入。
SORT_COLUMNS = {
    "added": "date(added_date)",  # 添加时间
    "rating": "rating",           # 评分
    "title": "title",             # 标题
}

app = Flask(__name__)
# flash 提示消息依赖 session,需要一个密钥。生产环境请换成随机值。
app.config["SECRET_KEY"] = "dev-secret-key-change-me"

# 请求结束时自动关闭数据库连接
app.teardown_appcontext(close_db)

# 启动时确保数据库和表已就绪(幂等,重复运行安全)
init_db()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def parse_form(form):
    """从提交的表单中读取字段,做基础清洗和校验。

    返回 (data, errors):
      - data:  整理好的字段字典,可直接用于 SQL 参数
      - errors: 校验错误信息列表,为空表示通过
    """
    title = form.get("title", "").strip()
    category = form.get("category", "").strip()
    status = form.get("status", "").strip()
    rating_raw = form.get("rating", "").strip()
    comment = form.get("comment", "").strip()
    # 日期留空则默认今天
    added_date = form.get("added_date", "").strip() or date.today().isoformat()

    errors = []
    if not title:
        errors.append("标题不能为空")
    if category not in CATEGORIES:
        errors.append("类型无效")
    if status not in STATUSES:
        errors.append("状态无效")

    # 评分可留空;填了就必须是 1-5 的整数
    rating = None
    if rating_raw:
        try:
            rating = int(rating_raw)
            if not 1 <= rating <= 5:
                errors.append("评分需在 1-5 之间")
                rating = None
        except ValueError:
            errors.append("评分必须是数字")

    data = {
        "title": title,
        "category": category,
        "status": status,
        "rating": rating,
        "comment": comment or None,  # 空字符串存成 NULL
        "added_date": added_date,
    }
    return data, errors


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """首页:添加表单 + 记录列表。

    支持通过 URL 查询参数做筛选 / 排序 / 搜索,条件可叠加:
      - category:  按类型筛选(空 = 全部)
      - status:    按状态筛选(空 = 全部)
      - q:         按标题模糊搜索(不区分大小写)
      - sort:      排序字段 added / rating / title(见 SORT_COLUMNS)
      - order:     排序方向 asc / desc
    筛选和排序都在 SQL 里完成,不把整表查出来再在 Python 里过滤。
    """
    # --- 读取并规范化查询参数(非法值一律回退到默认,顺带用于回显) ---
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "added")
    order = request.args.get("order", "desc")

    category = category if category in CATEGORIES else ""
    status = status if status in STATUSES else ""
    sort = sort if sort in SORT_COLUMNS else "added"
    order = "asc" if order == "asc" else "desc"

    # --- 组装 WHERE 条件(全部参数化,避免 SQL 注入) ---
    where = []
    params = {}
    if category:
        where.append("category = :category")
        params["category"] = category
    if status:
        where.append("status = :status")
        params["status"] = status
    if q:
        # SQLite 的 LIKE 对 ASCII 本就不区分大小写,这里显式 LOWER() 让行为更明确;
        # 中文没有大小写,不受影响。
        where.append("LOWER(title) LIKE :q")
        params["q"] = f"%{q.lower()}%"
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # --- 排序:字段和方向都已走白名单,可以安全拼接;追加 id 做稳定次级排序 ---
    direction = "ASC" if order == "asc" else "DESC"
    order_sql = f"ORDER BY {SORT_COLUMNS[sort]} {direction}, id {direction}"

    db = get_db()
    records = db.execute(
        f"SELECT * FROM records {where_sql} {order_sql}", params
    ).fetchall()

    return render_template(
        "index.html",
        records=records,
        categories=CATEGORIES,
        statuses=STATUSES,
        today=date.today().isoformat(),
        # 当前生效的条件,模板用它回显选中项(刷新/分享链接时保留状态)
        current={
            "category": category,
            "status": status,
            "q": q,
            "sort": sort,
            "order": order,
        },
    )


@app.route("/add", methods=["POST"])
def add():
    """新增一条记录。"""
    data, errors = parse_form(request.form)
    if errors:
        for msg in errors:
            flash(msg, "error")
        return redirect(url_for("index"))

    db = get_db()
    db.execute(
        "INSERT INTO records (title, category, status, rating, comment, added_date) "
        "VALUES (:title, :category, :status, :rating, :comment, :added_date)",
        data,
    )
    db.commit()
    flash("添加成功", "success")
    return redirect(url_for("index"))


@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
def edit(record_id):
    """编辑一条记录:GET 显示表单,POST 保存改动。"""
    db = get_db()
    record = db.execute(
        "SELECT * FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    if record is None:
        abort(404)  # 记录不存在

    if request.method == "POST":
        data, errors = parse_form(request.form)
        if errors:
            for msg in errors:
                flash(msg, "error")
            # 校验失败时,把用户刚填的内容回填,避免重填
            return render_template(
                "edit.html",
                record={**data, "id": record_id},
                categories=CATEGORIES,
                statuses=STATUSES,
            )

        db.execute(
            "UPDATE records SET title=:title, category=:category, status=:status, "
            "rating=:rating, comment=:comment, added_date=:added_date WHERE id=:id",
            {**data, "id": record_id},
        )
        db.commit()
        flash("修改成功", "success")
        return redirect(url_for("index"))

    # GET:展示带原值的编辑表单
    return render_template(
        "edit.html",
        record=record,
        categories=CATEGORIES,
        statuses=STATUSES,
    )


@app.route("/delete/<int:record_id>", methods=["POST"])
def delete(record_id):
    """删除一条记录。用 POST 提交,避免被爬虫/预取误触发。"""
    db = get_db()
    db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    db.commit()
    flash("已删除", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # debug=True 便于本地开发(改代码自动重载、报错页更详细)
    app.run(debug=True)
