# 个人观影 / 追番 / 读书记录 (v1.1)

一个用 Flask + SQLite 搭的最小记录工具:添加、编辑、删除你看过/想看的动画、电影、剧集、书、游戏，服务端渲染，无需前端框架。

## 功能

- 顶部表单添加记录：标题、类型、状态、评分(1-5，可留空)、短评(可留空)、添加日期(默认今天)
- 记录列表支持**筛选 / 排序 / 搜索**（v1.1 新增，详见下文）
- 每条记录可编辑、可删除
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

## 目录结构

```
media-tracker/
├── app.py              # Flask 应用主文件:路由、表单处理
├── db.py               # 数据库连接与初始化辅助
├── schema.sql          # 建表 SQL
├── templates/          # Jinja2 模板
│   ├── base.html       #   公共布局(标题、flash 消息)
│   ├── index.html      #   首页:添加表单 + 记录列表
│   └── edit.html       #   编辑页
├── static/
│   └── style.css       # 极简样式
├── requirements.txt    # 依赖清单
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
- `app.py` 里的 `SECRET_KEY` 只是本地开发用的占位值，用于显示提示消息；如果以后要部署到公网，请换成随机密钥。

## 后续可扩展方向（暂未实现）

- 统计图表（下一步）
- 接入外部 API 自动补全信息（如豆瓣、TMDB）
- 用户登录
