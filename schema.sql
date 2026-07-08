-- 数据库表结构:一张 records 表存放所有记录
-- 用 IF NOT EXISTS 保证重复执行也安全(幂等)
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键,自增
    title       TEXT    NOT NULL,                    -- 标题(必填)
    category    TEXT    NOT NULL,                    -- 类型:动画/电影/剧集/书/游戏
    status      TEXT    NOT NULL,                    -- 状态:想看/在看/看完
    rating      INTEGER,                             -- 评分 1-5,可为空
    comment     TEXT,                                -- 短评,可为空
    added_date  TEXT    NOT NULL                     -- 添加日期,格式 YYYY-MM-DD
);
