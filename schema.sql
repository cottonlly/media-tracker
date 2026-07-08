-- 数据库表结构:一张 records 表存放所有记录
-- 用 IF NOT EXISTS 保证重复执行也安全(幂等)
--
-- 注意:这里是「全新建库」的完整结构。给已存在的旧库补列的迁移逻辑在 db.py 的
-- _migrate() 里(SQLite 没有 ADD COLUMN IF NOT EXISTS,只能先查后加)。
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键,自增
    title       TEXT    NOT NULL,                    -- 标题(必填)
    category    TEXT    NOT NULL,                    -- 类型:动画/电影/剧集/书/游戏
    status      TEXT    NOT NULL,                    -- 状态:想看/在看/看完
    rating      INTEGER,                             -- 评分 1-5,可为空
    comment     TEXT,                                -- 短评,可为空
    added_date  TEXT    NOT NULL,                    -- 添加日期,格式 YYYY-MM-DD
    year        INTEGER,                             -- 年份(TMDB 自动填充,可空;v1.3)
    overview    TEXT,                                -- 简介(TMDB 自动填充,可空;v1.3)
    poster_url  TEXT                                 -- 海报图 URL(可空;v1.3)
);
