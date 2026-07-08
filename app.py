"""个人观影 / 追番 / 读书记录 —— Flask 应用主文件 (v1.4)。

功能:
  - 首页展示添加表单 + 记录列表
  - 列表支持筛选(类型 / 状态)、排序(添加时间 / 评分 / 标题,正倒序)、
    按标题模糊搜索;条件可叠加,并保存在 URL 查询参数里
  - 统计页(/stats):汇总数字 + 三张图表(类型分布 / 评分分布 / 每月看完),
    数据在 SQL 里聚合,前端用 Chart.js 渲染
  - 添加时按类型自动补全(见 /api/search):电影/剧集→TMDB、书→Open Library、
    动画→Bangumi,补全标题、年份、简介、封面;所有外部请求都在后端发起,
    密钥只从环境变量读取,前端拿不到
  - 新增 / 编辑 / 删除记录
  - 数据存在本地 SQLite 文件 media.db

运行:
  python app.py
然后浏览器打开 http://127.0.0.1:5000
"""

import os
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
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
STATUS_DONE = "看完"  # 「看完」状态字面量,统计页多处引用,抽出来避免散落的魔法字符串

# 允许的排序方式:URL 参数值 -> 对应的 SQL 排序表达式。
# ORDER BY 不能用参数占位符,只能拼字符串,所以必须用白名单防止 SQL 注入。
SORT_COLUMNS = {
    "added": "date(added_date)",  # 添加时间
    "rating": "rating",           # 评分
    "title": "title",             # 标题
}

# ---------------------------------------------------------------------------
# 自动补全 / 搜索:各数据源配置。所有外部请求都在后端发起(见 /api/search),
# 前端只调用本站接口、拿不到任何密钥。密钥只从环境变量读取,.env 由 dotenv 加载。
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).parent / ".env")  # 从项目根目录的 .env 读取

SEARCH_TIMEOUT = 6         # 请求外部 API 的超时(秒)
SEARCH_RESULT_LIMIT = 10   # 每次最多返回给前端的结果条数

# TMDB(电影 / 剧集):需要密钥,支持 v3 API Key 或 v4 Read Access Token
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/"  # 后接尺寸(如 w92)+ poster_path

# 标识本应用的 User-Agent。Bangumi 强制要求带上(否则可能被拒),Open Library 也建议带。
# 格式按 Bangumi 要求:用户名/项目名 (仓库地址)。
APP_USER_AGENT = "cottonlly/media-tracker (https://github.com/cottonlly/media-tracker)"

# Open Library(书):免费、无需 key / 无需认证
OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"
OPENLIBRARY_COVER = "https://covers.openlibrary.org/b/id/"  # 后接 {cover_i}-{尺寸}.jpg

# Bangumi(动画):公开 API、搜索无需 token
BANGUMI_SEARCH = "https://api.bgm.tv/search/subject/"  # 后接 URL 编码后的关键词
BANGUMI_TYPE_ANIME = 2     # Bangumi 条目类型:2 = 动画

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
    # v1.3 新增字段(可来自 TMDB 自动填充,也可手动填/改)
    year_raw = form.get("year", "").strip()
    overview = form.get("overview", "").strip()
    poster_url = form.get("poster_url", "").strip()

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

    # 年份可留空;填了就必须是合理范围内的整数
    year = None
    if year_raw:
        try:
            year = int(year_raw)
            if not 1800 <= year <= 2100:
                errors.append("年份需在 1800-2100 之间")
                year = None
        except ValueError:
            errors.append("年份必须是数字")

    data = {
        "title": title,
        "category": category,
        "status": status,
        "rating": rating,
        "comment": comment or None,      # 空字符串存成 NULL
        "added_date": added_date,
        "year": year,
        "overview": overview or None,
        "poster_url": poster_url or None,
    }
    return data, errors


class SearchError(Exception):
    """数据源返回的、可直接展示给用户的可预期错误(如关键词太短)。

    路由捕获它后原样把消息返回给前端(400),区别于网络 / 超时等技术性错误。
    """


def _tmdb_auth():
    """按密钥形态返回 (额外 query 参数, 额外请求头)。

    TMDB 有两种密钥,都能用于 v3 搜索接口,这里自动识别、填哪个都行:
      - v3 API Key:32 位字符,作为 query 参数 api_key 传;
      - v4 Read Access Token:JWT(含 '.'),作为 Bearer 放到 Authorization 头。
    """
    if "." in TMDB_API_KEY:  # v4 token 是 JWT,含点号
        return {}, {"Authorization": f"Bearer {TMDB_API_KEY}"}
    return {"api_key": TMDB_API_KEY}, {}


def search_tmdb(query):
    """在 TMDB 上搜索电影 + 剧集,合并、规范化后按热度返回前若干条。

    仅在后端使用密钥发起请求;返回给前端的每条结果只含展示 / 回填所需字段,
    不含密钥或多余原始数据。网络 / 超时等异常由调用方(路由)统一兜底处理。
    """
    auth_params, auth_headers = _tmdb_auth()
    found = []
    # (TMDB 接口路径, 归一到本项目的类型, 标题字段名, 首播/上映日期字段名)
    endpoints = [
        ("/search/movie", "电影", "title", "release_date"),
        ("/search/tv", "剧集", "name", "first_air_date"),
    ]
    for path, cat, title_key, date_key in endpoints:
        resp = requests.get(
            TMDB_API_BASE + path,
            params={
                **auth_params,
                "query": query,
                "language": "zh-CN",       # 优先中文标题 / 简介
                "include_adult": "false",
            },
            headers=auth_headers,
            timeout=SEARCH_TIMEOUT,
        )
        resp.raise_for_status()  # 401(密钥错) / 5xx 等在此抛 RequestException
        for item in resp.json().get("results", []):
            year = (item.get(date_key) or "")[:4]  # 日期形如 2010-07-16,取前四位
            poster_path = item.get("poster_path")
            found.append({
                "title": item.get(title_key) or "",
                "year": year,
                "media_type": cat,                 # 电影 / 剧集(正好是下拉里的选项)
                "overview": item.get("overview") or "",
                # 小图给结果列表用,较大图存进记录
                "poster_thumb": f"{TMDB_IMG_BASE}w92{poster_path}" if poster_path else "",
                "poster_url": f"{TMDB_IMG_BASE}w342{poster_path}" if poster_path else "",
                "popularity": item.get("popularity") or 0,
            })

    # 电影和剧集混在一起按热度降序,取前 N 条
    found.sort(key=lambda r: r["popularity"], reverse=True)
    return found[:SEARCH_RESULT_LIMIT]


def search_openlibrary(query):
    """在 Open Library 搜索图书(书)。免费、无需 key。

    返回结果的字段结构与 search_tmdb 保持一致,便于前端统一展示 / 回填。
    """
    resp = requests.get(
        OPENLIBRARY_SEARCH,
        params={
            "q": query,
            "limit": SEARCH_RESULT_LIMIT,
            # 只取需要的字段,减小响应体
            "fields": "title,first_publish_year,cover_i,author_name,first_sentence",
        },
        headers={"User-Agent": APP_USER_AGENT},
        timeout=SEARCH_TIMEOUT,
    )
    # Open Library 要求关键词至少 3 个字符,过短会返回 422,给出明确提示
    if resp.status_code == 422:
        raise SearchError("Open Library 要求关键词至少 3 个字符,请把书名写长一点或改用英文名")
    resp.raise_for_status()
    found = []
    for doc in resp.json().get("docs", []):
        cover_id = doc.get("cover_i")
        authors = doc.get("author_name") or []
        # first_sentence 可能是字符串或数组;没有则退回用作者名当简介
        sentence = doc.get("first_sentence")
        if isinstance(sentence, list):
            sentence = sentence[0] if sentence else ""
        overview = sentence or ("作者:" + "、".join(authors) if authors else "")
        year = doc.get("first_publish_year")
        found.append({
            "title": doc.get("title") or "",
            "year": str(year) if year else "",
            "media_type": "书",
            "overview": overview or "",
            "poster_thumb": f"{OPENLIBRARY_COVER}{cover_id}-S.jpg" if cover_id else "",
            "poster_url": f"{OPENLIBRARY_COVER}{cover_id}-M.jpg" if cover_id else "",
        })
    return found[:SEARCH_RESULT_LIMIT]


def search_bangumi(query):
    """在 Bangumi 搜索动画条目。公开接口、搜索无需 token。

    Bangumi 要求带上能标识调用方的 User-Agent,否则可能被拒绝(见 BANGUMI_USER_AGENT)。
    取中文标题(name_cn,缺失回退原名)、简介、封面图。字段结构与 search_tmdb 一致。
    """
    resp = requests.get(
        BANGUMI_SEARCH + quote(query),
        params={"type": BANGUMI_TYPE_ANIME, "responseGroup": "large",
                "max_results": SEARCH_RESULT_LIMIT},
        headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    # 无结果时 Bangumi 可能返回 {"results":0} 而没有 list 字段
    items = resp.json().get("list") or []
    found = []
    for item in items:
        images = item.get("images") or {}
        year = (item.get("air_date") or "")[:4]
        thumb = images.get("grid") or images.get("small") or ""
        poster = images.get("common") or images.get("medium") or images.get("large") or ""
        found.append({
            "title": item.get("name_cn") or item.get("name") or "",
            "year": year,
            "media_type": "动画",
            "overview": item.get("summary") or "",
            # Bangumi 返回的是 http:// 图片,升级到 https 以免将来 HTTPS 部署时被拦
            "poster_thumb": thumb.replace("http://", "https://", 1),
            "poster_url": poster.replace("http://", "https://", 1),
        })
    return found[:SEARCH_RESULT_LIMIT]


# 记录类型 -> (搜索函数, 数据源展示名)。前端按用户选的类型来这里查该调哪个 API。
# 未列出的类型(如「游戏」)= 暂不支持自动搜索,保持纯手动填写。
SEARCH_PROVIDERS = {
    "电影": (search_tmdb, "TMDB"),
    "剧集": (search_tmdb, "TMDB"),
    "书": (search_openlibrary, "Open Library"),
    "动画": (search_bangumi, "Bangumi"),
}


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


@app.route("/stats")
def stats():
    """统计页:顶部汇总数字 + 三张图表的数据。

    所有统计都在 SQL 里聚合完成,只把算好的小结果传给前端 Chart.js,
    不会把原始记录整表丢到浏览器再算。数据库为空 / 某类数据为零时,
    对应数字自然为 0、图表数据为空,页面照常渲染不报错。
    """
    db = get_db()
    year = str(date.today().year)  # 当前年份,形如 "2026"

    # --- 顶部卡片:四个汇总数字,一条查询算完 ---
    row = db.execute(
        "SELECT "
        "  COUNT(*) AS total, "
        "  COALESCE(SUM(CASE WHEN status = :done THEN 1 ELSE 0 END), 0) AS completed, "
        "  COALESCE(SUM(CASE WHEN status = :done "
        "                     AND strftime('%Y', added_date) = :year "
        "                    THEN 1 ELSE 0 END), 0) AS completed_this_year, "
        "  AVG(rating) AS avg_rating "  # 只对非空 rating 求平均;无评分时返回 NULL
        "FROM records",
        {"done": STATUS_DONE, "year": year},
    ).fetchone()

    summary = {
        "total": row["total"],
        "completed": row["completed"],
        "completed_this_year": row["completed_this_year"],
        # None 表示暂无评分,模板里显示「—」;有值则模板用 %.1f 保留一位小数
        "avg_rating": row["avg_rating"],
        "year": year,
    }

    # --- 图1:各类型数量(按 CATEGORIES 固定顺序,只保留有数据的类型) ---
    cat_counts = {
        r["category"]: r["n"]
        for r in db.execute(
            "SELECT category, COUNT(*) AS n FROM records GROUP BY category"
        ).fetchall()
    }
    category_labels = [c for c in CATEGORIES if cat_counts.get(c)]
    category_values = [cat_counts[c] for c in category_labels]

    # --- 图2:评分分布 1-5(补齐缺失分档为 0,保证 5 根柱子都在) ---
    rating_counts = {
        r["rating"]: r["n"]
        for r in db.execute(
            "SELECT rating, COUNT(*) AS n FROM records "
            "WHERE rating IS NOT NULL GROUP BY rating"
        ).fetchall()
    }
    rating_labels = ["1 分", "2 分", "3 分", "4 分", "5 分"]
    rating_values = [rating_counts.get(i, 0) for i in range(1, 6)]

    # --- 图3:按月统计「看完」数量(横轴月份,只列有数据的月份,按时间升序) ---
    month_rows = db.execute(
        "SELECT strftime('%Y-%m', added_date) AS ym, COUNT(*) AS n FROM records "
        "WHERE status = :done GROUP BY ym ORDER BY ym",
        {"done": STATUS_DONE},
    ).fetchall()
    month_labels = [r["ym"] for r in month_rows]
    month_values = [r["n"] for r in month_rows]

    return render_template(
        "stats.html",
        summary=summary,
        category_labels=category_labels,
        category_values=category_values,
        rating_labels=rating_labels,
        rating_values=rating_values,
        month_labels=month_labels,
        month_values=month_values,
    )


@app.route("/api/search")
def search():
    """自动补全搜索接口:按记录类型分发到对应数据源。

    前端把用户选好的类型(category)和关键词(q)传进来,后端据此决定调哪个 API
    (TMDB / Open Library / Bangumi)。所有外部请求都在后端发起,前端拿不到密钥。
    任一数据源搜不到、超时或报错都转成友好的 JSON 错误(带数据源名),页面不崩。
    """
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    if not query:
        return jsonify({"error": "请先输入标题再搜索"}), 400

    provider = SEARCH_PROVIDERS.get(category)
    if provider is None:
        # 游戏 / 未知类型:暂不支持自动搜索
        return jsonify(
            {"error": f"「{category or '该类型'}」暂不支持自动搜索,请手动填写"}
        ), 400
    search_func, source = provider

    # 只有 TMDB(电影 / 剧集)需要密钥,其它数据源免密钥
    if search_func is search_tmdb and not TMDB_API_KEY:
        return jsonify(
            {"error": "尚未配置 TMDB 密钥:请在 .env 里设置 TMDB_API_KEY 后重启"}
        ), 503

    try:
        results = search_func(query)
    except SearchError as e:
        # 可预期的、可直接展示的问题(如关键词太短)
        return jsonify({"error": str(e)}), 400
    except requests.Timeout:
        return jsonify({"error": f"{source} 搜索超时,请稍后重试"}), 504
    except requests.RequestException:
        # 网络错误、密钥无效、对方 5xx、返回非 JSON 等都归到这里
        return jsonify({"error": f"{source} 搜索失败,请检查网络后重试"}), 502

    return jsonify({"results": results, "source": source})


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
        "INSERT INTO records "
        "  (title, category, status, rating, comment, added_date, year, overview, poster_url) "
        "VALUES "
        "  (:title, :category, :status, :rating, :comment, :added_date, :year, :overview, :poster_url)",
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
            "rating=:rating, comment=:comment, added_date=:added_date, "
            "year=:year, overview=:overview, poster_url=:poster_url WHERE id=:id",
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
