# 个人观影 / 追番 / 读书记录 (v1.4)

一个用 Flask + SQLite 搭的最小记录工具:添加、编辑、删除你看过/想看的动画、电影、剧集、书、游戏，服务端渲染，无需前端框架。

## 功能

- 顶部表单添加记录：标题、类型、状态、评分(1-5，可留空)、年份、简介、海报、短评、添加日期(默认今天)
- 记录列表支持**筛选 / 排序 / 搜索**（v1.1 新增，详见下文）
- **统计页**：汇总数字 + 三张图表（v1.2 新增，详见下文）
- **添加时自动补全**：先选类型再点「搜索」，按类型自动调对应 API 补全标题、年份、简介、封面（电影/剧集→TMDB，书→Open Library，动画→Bangumi；v1.3–v1.4，详见下文）
- 每条记录可编辑、可删除，列表展示海报缩略图
- 数据保存在本地 SQLite 文件 `media.db`

## 筛选 / 排序 / 搜索（v1.1）

列表上方有一排控件，条件可以**叠加**生效，且全部保存在 URL 查询参数里 —— 刷新页面或把链接分享/收藏，条件都会保留：

- **类型筛选**：全部 / 动画 / 电影 / 剧集 / 书 / 游戏
- **状态筛选**：全部 / 想看 / 在看 / 看完
- **排序**：按添加时间 / 评分 / 标题，可选正序或倒序（默认：添加时间倒序）
- **搜索**：按标题关键词模糊匹配，不区分大小写（中文亦可）

点「应用」提交，点「重置」清空所有条件。

对应的 URL 参数（可手动拼接）：

| 参数       | 说明                    | 取值                                          |
| ---------- | ----------------------- | --------------------------------------------- |
| `category` | 类型筛选                | 动画 / 电影 / 剧集 / 书 / 游戏（留空=全部）    |
| `status`   | 状态筛选                | 想看 / 在看 / 看完（留空=全部）               |
| `sort`     | 排序字段                | `added`（添加时间，默认）/ `rating` / `title` |
| `order`    | 排序方向                | `desc`（倒序，默认）/ `asc`（正序）           |
| `q`        | 标题关键词              | 任意文本                                      |

例：类型=动画、状态=看完、按评分从高到低 —
`/?category=动画&status=看完&sort=rating&order=desc`

> 筛选和排序都在 SQL 查询里完成（不会把整表读出来再在内存里过滤）；`sort` / `order` 走白名单校验，非法值自动回退到默认，不存在 SQL 注入风险。

## 统计页（v1.2）

顶部导航点「统计」进入 `/stats`（也可从统计页点「列表」返回）。页面包含：

- **四个汇总卡片**：记录总数、已看完总数、今年（当年）看完数量、平均评分（只统计有评分的记录，保留一位小数；无评分时显示 `—`）
- **三张图表**（用 [Chart.js](https://www.chartjs.org/) 绘制）：
  - 各类型数量 —— 环形图
  - 评分分布（1~5 分各多少条）—— 柱状图
  - 每月「看完」数量 —— 柱状图（横轴为月份，取自记录的添加日期）

实现要点：

- 所有统计都由 **Flask 后端在 SQL 里聚合**算好，只把结果（几组标签和数字）传给前端，Chart.js 只负责画图 —— 不会把原始记录整表丢到浏览器。
- Chart.js 通过 **CDN** 引入（`cdn.jsdelivr.net`），无需构建工具；因此**查看统计页需要联网**（列表等其余页面离线也能用）。
- 数据库为空、或某类数据为零时页面照常显示：数字为 `0`、平均评分显示 `—`、对应图表标注「暂无数据」，不会报错。

## 添加时自动补全（v1.3–v1.4）

添加记录时，**先选好「类型」**，在标题框旁点「搜索」：后端会**按类型自动选择数据源**去搜，列出匹配结果（每条显示封面小图、标题、年份、类型）；点选一条即自动把**标题、年份、简介、封面图 URL** 填进表单，你仍可手动修改后再保存。列表和编辑页都会展示封面缩略图。

按类型走不同 API：

| 类型 | 数据源 | 是否需要 key |
| ---- | ------ | ------------ |
| 电影 / 剧集 | [TMDB](https://www.themoviedb.org/) | 需要（见下） |
| 书 | [Open Library](https://openlibrary.org/) | 不需要 |
| 动画 | [Bangumi](https://bgm.tv/) | 不需要 |
| 游戏 | —（暂纯手动填写） | — |

> 后端把「调哪个 API」按类型分发到各自的搜索函数（`search_tmdb` / `search_openlibrary` / `search_bangumi`），统一成同样的结果结构给前端复用。只有 TMDB 需要配 key，另外两个开箱即用。

### 各数据源说明

- **Open Library（书）**：免费、无需认证。注意它要求关键词**至少 3 个字符**，过短（如两字中文书名）会提示你写长一点或改用英文名。
- **Bangumi（动画）**：公开接口、搜索无需 token，但请求会带上标识本应用的 `User-Agent`（Bangumi 的要求）。取中文标题、简介、封面。
- **TMDB（电影 / 剧集）**：需要 key，配置见下。

### 1. 申请 TMDB API Key

1. 注册并登录 [www.themoviedb.org](https://www.themoviedb.org/)
2. 打开 **Settings → API**（[直达链接](https://www.themoviedb.org/settings/api)）
3. 申请一个开发用 API Key（类型选 Developer，按提示填用途即可）
4. 复制页面上的 **API Key (v3 auth)**（32 位字符）**或** **API Read Access Token (v4)**（`eyJ...` 开头的一长串 token）—— 两种都能用，程序会自动识别

### 2. 配置到 .env

项目根目录已有一个 `.env` 文件（**已被 `.gitignore` 忽略，不会提交到 GitHub**）。把 key 填进去：

```
TMDB_API_KEY=你复制的APIKey
```

> - 若没有 `.env`，可复制 `.env.example` 为 `.env` 再填。
> - `.env.example` 只列变量名、不含真实 key，用来告诉别人（和以后的你）需要配哪些环境变量。
> - 改完 `.env` 后需**重启** `python app.py` 才生效。

### 说明与容错

- 所有外部请求**只在后端发起**：前端点「搜索」时调用本项目的 `/api/search?q=...&category=...`，由 Flask 用 `requests` 去请求对应数据源，浏览器里看不到任何 key。
- 需**联网**才能搜索；搜索功能不可用不影响手动添加记录。
- **未配置 key、关键词过短、搜不到结果、请求失败或超时**都会给出对应的友好提示（并标明是哪个数据源），不会让页面崩掉；某个数据源出问题也不影响其它类型。

## 目录结构

```
media-tracker/
├── app.py              # Flask 应用主文件:路由、表单处理、多数据源搜索代理
├── db.py               # 数据库连接、建表、迁移(给旧库补列)
├── schema.sql          # 建表 SQL(全新建库用)
├── templates/          # Jinja2 模板
│   ├── base.html       #   公共布局(标题、导航、flash 消息)
│   ├── index.html      #   首页:添加表单(含搜索 TMDB) + 记录列表
│   ├── edit.html       #   编辑页
│   └── stats.html      #   统计页:汇总卡片 + Chart.js 图表
├── static/
│   └── style.css       # 极简样式
├── requirements.txt    # 依赖清单(Flask / requests / python-dotenv)
├── .env.example        # 环境变量示例(只有变量名,可提交)
├── .env                # 本地环境变量(含密钥,已被 .gitignore 忽略)
├── .gitignore
└── README.md
```

## 安装依赖

需要 Python 3.8 以上。建议用虚拟环境隔离依赖。

### Windows (PowerShell)

```powershell
cd media-tracker
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> 如果 PowerShell 提示脚本被禁止运行，先执行一次：
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### macOS / Linux

```bash
cd media-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

首次启动会自动创建数据库文件 `media.db`。然后浏览器打开：

```
http://127.0.0.1:5000
```

按 `Ctrl + C` 停止服务。

## 说明

- 数据库文件 `media.db` 已在 `.gitignore` 中忽略，删掉它即可清空所有数据、重新开始。
- **升级兼容**：启动时会自动给已有数据库补上新增的列（如 v1.3 的 `year` / `overview` / `poster_url`），老记录这些字段留空即可，不会报错、也不会丢数据。
- `.env` 存放密钥，已被忽略、不会进版本库；分享项目时只会带上 `.env.example`。
- `app.py` 里的 `SECRET_KEY` 只是本地开发用的占位值，用于显示提示消息；如果以后要部署到公网，请换成随机密钥。

## 后续可扩展方向（暂未实现）

- 游戏类型的自动补全（如 IGDB / RAWG）
- 界面美化
- 标签
- 用户登录
