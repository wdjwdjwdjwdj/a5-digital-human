"""景区数据仓储层：封装 5 张 SQLite 表的 CRUD 操作。

参考 chat_repo.py 的辅助方法模式（_execute, _fetchone, _fetchall）。
使用 PRAGMA journal_mode=WAL 和 PRAGMA foreign_keys=ON。
种子数据在首次查询表为空时自动插入，不依赖外部 SQL 脚本。
"""

import asyncio
import logging
import random
import sqlite3
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── 建表 SQL ───────────────────────────────────────────────

_CREATE_AREA_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_area_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    ticket_info TEXT,
    phone TEXT,
    open_hours TEXT,
    rating REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_SPOTS_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    position TEXT,
    lat REAL,
    lng REAL,
    rating REAL,
    highlights TEXT,
    description TEXT,
    image_url TEXT,
    open_hours TEXT,
    ticket_price TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_ACTIVITIES_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    time TEXT,
    location TEXT,
    tags TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_ROUTES_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    duration TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_ROUTE_SPOTS_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_route_spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    spot_id INTEGER NOT NULL,
    spot_order INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (route_id) REFERENCES scenic_routes(id),
    FOREIGN KEY (spot_id) REFERENCES scenic_spots(id)
)
"""

_CREATE_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS scenic_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_CONFIG_DEFAULTS: dict[str, str] = {
    "scenic_name": "灵山胜境",
    "guide_name": "灵灵",
    "ai_persona": (
        "你是无锡灵山胜境智能导游'灵灵'。热情专业口语化，"
        "介绍佛教文化/景点/历史/路线/美食。"
        "回答≤100字。末尾附[情绪:happy/sad/angry/surprise/neutral]。"
    ),
    "default_tts_voice": "zh-CN-XiaoxiaoNeural",
}

# ── 种子数据 ───────────────────────────────────────────────

_SEED_AREA: dict = {
    "name": "灵山胜境",
    "description": (
        "灵山胜境位于江苏省无锡市太湖之滨，是国家AAAAA级旅游景区，"
        "以佛教文化为主题，集湖光山色、佛教建筑、文化体验于一体。"
        "核心景点灵山大佛高88米，为青铜铸造，庄严肃穆。"
        "景区内梵宫、九龙灌浴、五印坛城等建筑气势恢宏，"
        "融合了传统佛教艺术与现代建筑技术。"
    ),
    "ticket_info": "成人票210元，学生票105元，老人票105元（60-69周岁），70周岁以上免票",
    "phone": "0510-85681166",
    "open_hours": "8:00-17:00（夏季8:00-17:30）",
    "rating": 4.8,
}

_SEED_SPOTS: list[dict] = [
    {"spot_id": "LS-001", "name": "灵山大照壁", "category": "文化景观",
     "position": "景区入口处", "rating": 4.7, "ticket_price": "免费",
     "highlights": "华夏第一照壁",
     "description": "灵山大照壁位于景区入口，长38.4米，高8.4米，"
     "正面镌刻灵山胜境四个大字，背面刻有《灵山赋》。"},
    {"spot_id": "LS-002", "name": "五明桥", "category": "建筑景观",
     "position": "大照壁后方", "rating": 4.6, "ticket_price": "免费",
     "highlights": "佛教五明文化",
     "description": "五明桥横跨放生池，桥身刻有佛教五明图案。"
     "桥栏雕刻精美，寓意智慧与慈悲，是进入灵山胜境的重要通道。"},
    {"spot_id": "LS-003", "name": "佛足坛", "category": "佛教景观",
     "position": "五明桥左侧", "rating": 4.5, "ticket_price": "免费",
     "highlights": "释迦牟尼足迹",
     "description": "佛足坛内供奉着仿释迦牟尼足迹的巨型石雕佛足，"
     "长1.2米，宽0.6米，足底刻有法轮、宝瓶等吉祥图案。"},
    {"spot_id": "LS-004", "name": "五智门", "category": "建筑景观",
     "position": "佛足坛前方", "rating": 4.6, "ticket_price": "免费",
     "highlights": "佛教五智",
     "description": "五智门是一座气势宏伟的石牌坊，高12米，宽18米，"
     "是灵山胜境的标志性门楼。"},
    {"spot_id": "LS-005", "name": "菩提大道", "category": "景观通道",
     "position": "五智门至九龙灌浴", "rating": 4.7, "ticket_price": "免费",
     "highlights": "智慧之路",
     "description": "菩提大道全长约300米，宽20米，两侧种植菩提树，"
     "地面铺设莲花图案石板。大道尽头可远眺灵山大佛。"},
    {"spot_id": "LS-006", "name": "九龙灌浴", "category": "动态景观",
     "position": "菩提大道尽头", "rating": 4.9,
     "ticket_price": "免费（含门票）", "highlights": "动态音乐喷泉群雕",
     "description": "九龙灌浴是灵山胜境最壮观的动态景观，"
     "高27.5米的青铜群雕配合音乐喷泉，"
     "再现释迦牟尼诞生时九龙灌浴、花开见佛的圣景。"},
    {"spot_id": "LS-007", "name": "降魔浮雕", "category": "佛教景观",
     "position": "九龙灌浴西侧", "rating": 4.7, "ticket_price": "免费",
     "highlights": "降魔成道故事",
     "description": "降魔浮雕长26米，高8米，以青铜铸造，"
     "生动刻画了释迦牟尼在菩提树下降伏魔罗、证悟成佛的故事。"},
    {"spot_id": "LS-008", "name": "阿育王柱", "category": "文化景观",
     "position": "降魔浮雕前方", "rating": 4.5, "ticket_price": "免费",
     "highlights": "古代印度风格石柱",
     "description": "阿育王柱高20米，重约200吨，仿印度鹿野苑阿育王柱建造。"
     "柱身刻有佛教法轮和狮子雕像。"},
    {"spot_id": "LS-009", "name": "百子戏弥勒", "category": "雕塑景观",
     "position": "阿育王柱北侧", "rating": 4.8, "ticket_price": "免费",
     "highlights": "百童嬉戏弥勒雕像",
     "description": "百子戏弥勒是一尊大型青铜雕塑，弥勒佛高约8米，"
     "佛身周围塑有100个形态各异的童子，寓意大肚能容、笑口常开。"},
    {"spot_id": "LS-010", "name": "祥符禅寺", "category": "寺庙建筑",
     "position": "景区中轴线上", "rating": 4.8,
     "ticket_price": "免费（含门票）", "highlights": "千年古刹",
     "description": "祥符禅寺始建于唐代，寺内供奉着释迦牟尼、观音菩萨等"
     "佛教圣像，建筑风格为明清江南寺院风格。"},
    {"spot_id": "LS-011", "name": "灵山大佛", "category": "标志景观",
     "position": "景区最高处", "rating": 4.9,
     "ticket_price": "免费（含门票）", "highlights": "88米青铜大佛",
     "description": "灵山大佛高88米，青铜铸造，重约700吨，"
     "是世界上最高的青铜立佛之一。大佛右手施施愿印，左手施说法印。"},
    {"spot_id": "LS-012", "name": "佛教文化博览馆", "category": "文化场馆",
     "position": "灵山大佛基座内", "rating": 4.7,
     "ticket_price": "免费（含门票）", "highlights": "佛教艺术珍品",
     "description": "佛教文化博览馆建筑面积约1.2万平方米，"
     "馆内收藏展示了汉传、藏传、南传佛教的各类艺术珍品。"},
    {"spot_id": "LS-013", "name": "灵山梵宫", "category": "建筑景观",
     "position": "景区东侧", "rating": 4.9,
     "ticket_price": "免费（含门票）", "highlights": "梵宫穹顶艺术",
     "description": "灵山梵宫建筑面积达7.2万平方米，"
     "宫内穹顶采用大型彩绘玻璃，华美绝伦。"},
    {"spot_id": "LS-014", "name": "五印坛城", "category": "宗教建筑",
     "position": "梵宫东侧", "rating": 4.6,
     "ticket_price": "免费（含门票）", "highlights": "藏传佛教风格",
     "description": "五印坛城高约30米，坛城内供奉着五方佛，"
     "建筑外观金碧辉煌，内部壁画精美绝伦。"},
    {"spot_id": "LS-015", "name": "曼飞龙塔", "category": "建筑景观",
     "position": "五印坛城南侧", "rating": 4.5,
     "ticket_price": "免费（含门票）", "highlights": "南传佛教风格白塔",
     "description": "曼飞龙塔仿云南西双版纳曼飞龙塔建造，塔身洁白，塔尖金黄。"},
    {"spot_id": "LS-016", "name": "无尽意斋", "category": "文化景观",
     "position": "景区北侧", "rating": 4.6,
     "ticket_price": "免费（含门票）", "highlights": "禅意文化空间",
     "description": "无尽意斋名称取自佛教无尽意菩萨，"
     "斋内设有茶室、抄经堂、禅修室等。"},
]

_SEED_ACTIVITIES: list[dict] = [
    {"name": "九龙灌浴表演", "time": "每日 10:00、11:30、14:00、16:00",
     "location": "九龙灌浴广场", "tags": "演出,必看,亲子",
     "description": "大型动态音乐喷泉表演，再现佛陀诞生圣景。每场约15分钟。"},
    {"name": "灵山吉祥颂", "time": "每日 14:30",
     "location": "灵山梵宫圣坛", "tags": "演出,文化,震撼",
     "description": "大型音乐史诗演出，运用穹顶投影、灯光音响等现代科技。每场约30分钟。"},
    {"name": "禅茶一味体验", "time": "每日 09:00-11:00, 13:00-16:00",
     "location": "无尽意斋", "tags": "体验,文化,雅致",
     "description": "由茶艺师指导品茗静心。每场约40分钟，需提前预约。"},
    {"name": "抄经静心活动", "time": "每日 09:00-17:00",
     "location": "无尽意斋", "tags": "体验,文化,静心",
     "description": "提供毛笔、宣纸和经书模板，在静谧的禅意空间中抄写经文。随到随体验。"},
]

_SEED_ROUTES: list[dict] = [
    {"name": "经典祈福线路", "duration": "约3小时",
     "description": "大照壁 -> 五明桥 -> 佛足坛 -> 五智门 -> 菩提大道 -> "
     "九龙灌浴 -> 降魔浮雕 -> 阿育王柱 -> 百子戏弥勒 -> 祥符禅寺 -> "
     "灵山大佛 -> 佛教文化博览馆"},
    {"name": "全景深度游线路", "duration": "约5小时",
     "description": "大照壁 -> 五明桥 -> 佛足坛 -> 五智门 -> 菩提大道 -> "
     "九龙灌浴 -> 降魔浮雕 -> 阿育王柱 -> 百子戏弥勒 -> 祥符禅寺 -> "
     "灵山大佛 -> 佛教文化博览馆 -> 灵山梵宫 -> 五印坛城 -> 曼飞龙塔 -> 无尽意斋"},
    {"name": "文化体验线路", "duration": "约4小时",
     "description": "九龙灌浴 -> 灵山梵宫（含吉祥颂） -> 五印坛城 -> "
     "曼飞龙塔 -> 佛教文化博览馆 -> 无尽意斋（禅茶/抄经）"},
]

_SEED_ROUTE_SPOTS: list[tuple[int, str, int]] = [
    (1, "LS-001", 1), (1, "LS-002", 2), (1, "LS-003", 3), (1, "LS-004", 4),
    (1, "LS-005", 5), (1, "LS-006", 6), (1, "LS-007", 7), (1, "LS-008", 8),
    (1, "LS-009", 9), (1, "LS-010", 10), (1, "LS-011", 11), (1, "LS-012", 12),
    (2, "LS-001", 1), (2, "LS-002", 2), (2, "LS-003", 3), (2, "LS-004", 4),
    (2, "LS-005", 5), (2, "LS-006", 6), (2, "LS-007", 7), (2, "LS-008", 8),
    (2, "LS-009", 9), (2, "LS-010", 10), (2, "LS-011", 11), (2, "LS-012", 12),
    (2, "LS-013", 13), (2, "LS-014", 14), (2, "LS-015", 15), (2, "LS-016", 16),
    (3, "LS-006", 1), (3, "LS-013", 2), (3, "LS-014", 3),
    (3, "LS-015", 4), (3, "LS-012", 5), (3, "LS-016", 6),
]


class ScenicRepository:
    """景区数据仓储层，封装 5 张景区相关 SQLite 表的 CRUD 操作。"""

    def __init__(self, db_path: str) -> None:
        """初始化 ScenicRepository。

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接（WAL 模式 + 外键约束）。

        Returns:
            sqlite3.Connection 对象
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL（同步，由 asyncio.to_thread 包装调用）。

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            sqlite3.Cursor
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor
        except Exception:
            try:
                conn.rollback()
            except Exception:
                logger.warning("[ScenicRepo] rollback 失败: %s", traceback.format_exc())
            raise
        finally:
            conn.close()

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """查询单行（同步）。

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            字典形式的行数据，无结果返回 None
        """
        conn = self._get_connection()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多行（同步）。

        Args:
            sql: SQL 语句
            params: 参数元组

        Returns:
            字典列表
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def init_db(self) -> None:
        """初始化数据库表结构（CREATE TABLE IF NOT EXISTS）。"""
        try:
            await asyncio.to_thread(self._execute, _CREATE_AREA_TABLE)
            await asyncio.to_thread(self._execute, _CREATE_SPOTS_TABLE)
            await asyncio.to_thread(self._execute, _CREATE_ACTIVITIES_TABLE)
            await asyncio.to_thread(self._execute, _CREATE_ROUTES_TABLE)
            await asyncio.to_thread(self._execute, _CREATE_ROUTE_SPOTS_TABLE)
            await asyncio.to_thread(self._execute, _CREATE_CONFIG_TABLE)
            logger.info("[ScenicRepo] 数据库表初始化完成")
        except Exception:
            logger.error("[ScenicRepo] 数据库表初始化失败: %s", traceback.format_exc())
            raise

    async def init_seed_data(self) -> None:
        """初始化种子数据，仅在表为空时插入（INSERT OR IGNORE 防重复）。"""
        try:
            existing = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_area_info"
            )
            if existing and existing["cnt"] == 0:
                await asyncio.to_thread(
                    self._execute,
                    "INSERT OR IGNORE INTO scenic_area_info "
                    "(name, description, ticket_info, phone, open_hours, rating) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (_SEED_AREA["name"], _SEED_AREA["description"], _SEED_AREA["ticket_info"],
                     _SEED_AREA["phone"], _SEED_AREA["open_hours"], _SEED_AREA["rating"]),
                )
                logger.info("[ScenicRepo] 景区基础信息种子数据已插入")

            existing_spots = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_spots"
            )
            if existing_spots and existing_spots["cnt"] == 0:
                for spot in _SEED_SPOTS:
                    await asyncio.to_thread(
                        self._execute,
                        "INSERT OR IGNORE INTO scenic_spots "
                        "(spot_id, name, category, position, rating, highlights, description, ticket_price) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (spot["spot_id"], spot["name"], spot["category"], spot["position"],
                         spot["rating"], spot["highlights"], spot["description"], spot["ticket_price"]),
                    )
                logger.info("[ScenicRepo] 景点种子数据已插入 (%d 条)", len(_SEED_SPOTS))

            existing_acts = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_activities"
            )
            if existing_acts and existing_acts["cnt"] == 0:
                for act in _SEED_ACTIVITIES:
                    await asyncio.to_thread(
                        self._execute,
                        "INSERT OR IGNORE INTO scenic_activities "
                        "(name, time, location, tags, description) VALUES (?, ?, ?, ?, ?)",
                        (act["name"], act["time"], act["location"], act["tags"], act["description"]),
                    )
                logger.info("[ScenicRepo] 活动种子数据已插入 (%d 条)", len(_SEED_ACTIVITIES))

            existing_routes = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_routes"
            )
            if existing_routes and existing_routes["cnt"] == 0:
                for route in _SEED_ROUTES:
                    await asyncio.to_thread(
                        self._execute,
                        "INSERT OR IGNORE INTO scenic_routes "
                        "(name, duration, description) VALUES (?, ?, ?)",
                        (route["name"], route["duration"], route["description"]),
                    )
                logger.info("[ScenicRepo] 路线种子数据已插入 (%d 条)", len(_SEED_ROUTES))

            existing_rs = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_route_spots"
            )
            if existing_rs and existing_rs["cnt"] == 0:
                spot_rows = await asyncio.to_thread(
                    self._fetchall, "SELECT id, spot_id FROM scenic_spots"
                )
                spot_id_map = {r["spot_id"]: r["id"] for r in spot_rows}
                route_rows = await asyncio.to_thread(
                    self._fetchall, "SELECT id FROM scenic_routes ORDER BY id"
                )
                for route_idx, spot_sid, spot_order in _SEED_ROUTE_SPOTS:
                    rid = route_rows[route_idx - 1]["id"]
                    sid = spot_id_map.get(spot_sid)
                    if sid is None:
                        logger.warning("[ScenicRepo] 路线-景点关联跳过未知 spot_id: %s", spot_sid)
                        continue
                    await asyncio.to_thread(
                        self._execute,
                        "INSERT OR IGNORE INTO scenic_route_spots "
                        "(route_id, spot_id, spot_order) VALUES (?, ?, ?)",
                        (rid, sid, spot_order),
                    )
                logger.info("[ScenicRepo] 路线-景点关联种子数据已插入 (%d 条)", len(_SEED_ROUTE_SPOTS))

            logger.info("[ScenicRepo] 种子数据初始化完成")
        except Exception:
            logger.error("[ScenicRepo] 种子数据初始化失败: %s", traceback.format_exc())
            raise

    # ── 查询方法 ───────────────────────────────────────────

    async def get_area_info(self) -> dict | None:
        """获取景区基础信息。"""
        try:
            return await asyncio.to_thread(
                self._fetchone, "SELECT * FROM scenic_area_info ORDER BY id LIMIT 1"
            )
        except Exception:
            logger.error("[ScenicRepo] 查询景区信息失败: %s", traceback.format_exc())
            return None

    async def get_spots(self, category: str | None = None) -> list[dict]:
        """获取景点列表，支持按 category 过滤。

        Args:
            category: 景点分类（可选）

        Returns:
            景点字典列表
        """
        try:
            if category:
                return await asyncio.to_thread(
                    self._fetchall,
                    "SELECT * FROM scenic_spots WHERE category = ? ORDER BY spot_id",
                    (category,),
                )
            return await asyncio.to_thread(
                self._fetchall, "SELECT * FROM scenic_spots ORDER BY spot_id"
            )
        except Exception:
            logger.error("[ScenicRepo] 查询景点列表失败: %s", traceback.format_exc())
            return []

    async def get_spot_by_spot_id(self, spot_id: str) -> dict | None:
        """根据 spot_id 获取单个景点详情。

        Args:
            spot_id: 景点唯一标识（如 LS-011）

        Returns:
            景点字典，未找到返回 None
        """
        try:
            return await asyncio.to_thread(
                self._fetchone, "SELECT * FROM scenic_spots WHERE spot_id = ?", (spot_id,)
            )
        except Exception:
            logger.error("[ScenicRepo] 查询景点详情失败: %s", traceback.format_exc())
            return None

    async def create_spot(self, data: dict) -> dict | None:
        """新增景点。

        Args:
            data: 景点数据字典

        Returns:
            新创建的景点字典，失败返回 None
        """
        try:
            spot_id = data.get("spot_id") or await self._next_spot_id()
            await asyncio.to_thread(
                self._execute,
                "INSERT INTO scenic_spots "
                "(spot_id, name, category, position, highlights, description, rating, ticket_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (spot_id, data["name"], data["category"], data.get("position", ""),
                 data.get("highlights", ""), data.get("description", ""),
                 data.get("rating", 0.0), data.get("ticket_price", "免费")),
            )
            return await self.get_spot_by_spot_id(spot_id)
        except Exception:
            logger.error("[ScenicRepo] 新增景点失败: %s", traceback.format_exc())
            return None

    async def _next_spot_id(self) -> str:
        """生成下一个 spot_id（LS-XXX 格式）。

        Returns:
            下一个可用的 spot_id
        """
        rows = await asyncio.to_thread(
            self._fetchall,
            "SELECT spot_id FROM scenic_spots WHERE spot_id LIKE 'LS-%' ORDER BY spot_id DESC LIMIT 1",
        )
        if rows:
            last_id = rows[0]["spot_id"]
            try:
                num = int(last_id.split("-")[1]) + 1
            except (ValueError, IndexError):
                num = 17
        else:
            num = 1
        return f"LS-{num:03d}"

    async def update_spot(self, spot_id: str, data: dict) -> dict | None:
        """更新景点信息。

        Args:
            spot_id: 景点唯一标识
            data: 要更新的字段字典

        Returns:
            更新后的景点字典，未找到返回 None
        """
        try:
            existing = await self.get_spot_by_spot_id(spot_id)
            if not existing:
                return None
            fields: list[str] = []
            params: list = []
            for key in ("name", "category", "position", "highlights", "description", "rating", "ticket_price"):
                if key in data:
                    fields.append(f"{key} = ?")
                    params.append(data[key])
            if not fields:
                return existing
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(spot_id)
            await asyncio.to_thread(
                self._execute,
                f"UPDATE scenic_spots SET {', '.join(fields)} WHERE spot_id = ?",
                tuple(params),
            )
            return await self.get_spot_by_spot_id(spot_id)
        except Exception:
            logger.error("[ScenicRepo] 更新景点失败: %s", traceback.format_exc())
            return None

    async def delete_spot(self, spot_id: str) -> bool:
        """删除景点。

        Args:
            spot_id: 景点唯一标识

        Returns:
            是否成功删除
        """
        try:
            cursor = await asyncio.to_thread(
                self._execute, "DELETE FROM scenic_spots WHERE spot_id = ?", (spot_id,)
            )
            return cursor.rowcount > 0
        except Exception:
            logger.error("[ScenicRepo] 删除景点失败: %s", traceback.format_exc())
            return False

    async def get_activities(self) -> list[dict]:
        """获取活动列表。"""
        try:
            return await asyncio.to_thread(
                self._fetchall, "SELECT * FROM scenic_activities ORDER BY id"
            )
        except Exception:
            logger.error("[ScenicRepo] 查询活动列表失败: %s", traceback.format_exc())
            return []

    async def get_routes(self) -> list[dict]:
        """获取路线列表（每条路线含关联景点列表）。"""
        try:
            routes = await asyncio.to_thread(
                self._fetchall, "SELECT * FROM scenic_routes ORDER BY id"
            )
            for route in routes:
                spots = await asyncio.to_thread(
                    self._fetchall,
                    "SELECT s.*, rs.spot_order FROM scenic_spots s "
                    "JOIN scenic_route_spots rs ON s.id = rs.spot_id "
                    "WHERE rs.route_id = ? ORDER BY rs.spot_order",
                    (route["id"],),
                )
                route["spots"] = spots
            return routes
        except Exception:
            logger.error("[ScenicRepo] 查询路线列表失败: %s", traceback.format_exc())
            return []

    async def get_route_by_id(self, route_id: int) -> dict | None:
        """获取单个路线详情（含关联景点）。

        Args:
            route_id: 路线 ID

        Returns:
            路线字典（含 spots 列表），未找到返回 None
        """
        try:
            route = await asyncio.to_thread(
                self._fetchone, "SELECT * FROM scenic_routes WHERE id = ?", (route_id,)
            )
            if not route:
                return None
            spots = await asyncio.to_thread(
                self._fetchall,
                "SELECT s.*, rs.spot_order FROM scenic_spots s "
                "JOIN scenic_route_spots rs ON s.id = rs.spot_id "
                "WHERE rs.route_id = ? ORDER BY rs.spot_order",
                (route_id,),
            )
            route["spots"] = spots
            return route
        except Exception:
            logger.error("[ScenicRepo] 查询路线详情失败: %s", traceback.format_exc())
            return None

    async def get_stats(self) -> dict:
        """获取景区统计数据（含 dashboard 大屏完整数据）。

        Returns:
            {spot_count, activity_count, route_count, today_visitors,
             current_visitors, satisfaction, ai_conversations, daily_visits}
        """
        result: dict = {
            "spot_count": 0, "activity_count": 0, "route_count": 0,
            "today_visitors": 0, "current_visitors": 0,
            "satisfaction": 96.8, "ai_conversations": 0,
            "daily_visits": [],
        }
        try:
            spot_cnt = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_spots"
            )
            act_cnt = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_activities"
            )
            route_cnt = await asyncio.to_thread(
                self._fetchone, "SELECT COUNT(*) as cnt FROM scenic_routes"
            )
            if spot_cnt:
                result["spot_count"] = spot_cnt["cnt"]
            if act_cnt:
                result["activity_count"] = act_cnt["cnt"]
            if route_cnt:
                result["route_count"] = route_cnt["cnt"]

            # ── 模拟客流数据 ──
            spot_n = result["spot_count"] or 16
            result["today_visitors"] = spot_n * random.randint(50, 150)
            result["current_visitors"] = random.randint(200, 800)

            # ── AI 对话总数（从 conversations 表查询，失败时模拟） ──
            try:
                conv_cnt = await asyncio.to_thread(
                    self._fetchone, "SELECT COUNT(*) as cnt FROM conversations"
                )
                if conv_cnt:
                    result["ai_conversations"] = conv_cnt["cnt"]
            except Exception:
                result["ai_conversations"] = random.randint(800, 2000)

            # ── 近 7 日客流趋势（模拟数据） ──
            daily_visits: list[dict] = []
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                daily_visits.append({
                    "date": day,
                    "visitors": random.randint(800, 2000),
                    "conversations": random.randint(30, 120),
                })
            result["daily_visits"] = daily_visits
        except Exception:
            logger.error("[ScenicRepo] 查询统计失败: %s", traceback.format_exc())
        return result

    async def get_ai_responses(self) -> list[dict]:
        """获取 AI 常见问答配置（从景区基础信息生成）。"""
        area = await self.get_area_info()
        if not area:
            return []
        return [
            {"question": "景区名称", "answer": area.get("name", "")},
            {"question": "景区简介", "answer": area.get("description", "")},
            {"question": "门票信息", "answer": area.get("ticket_info", "")},
            {"question": "开放时间", "answer": area.get("open_hours", "")},
            {"question": "联系电话", "answer": area.get("phone", "")},
            {"question": "景区评分", "answer": f"{area.get('rating', '')} 分"},
        ]

    # ── 配置管理 ───────────────────────────────────────────

    async def get_config(self) -> dict[str, str]:
        """从 scenic_config 表加载配置，与默认值合并。

        Returns:
            完整配置字典
        """
        try:
            rows = await asyncio.to_thread(
                self._fetchall, "SELECT key, value FROM scenic_config"
            )
            db_config = {row["key"]: row["value"] for row in rows}
            merged = dict(_CONFIG_DEFAULTS)
            merged.update(db_config)
            return merged
        except Exception:
            logger.error("[ScenicRepo] 加载配置失败: %s", traceback.format_exc())
            return dict(_CONFIG_DEFAULTS)

    async def save_config(self, config: dict[str, str]) -> dict[str, str]:
        """保存配置到 scenic_config 表（upsert）。"""
        try:
            for key, value in config.items():
                if value is not None:
                    await asyncio.to_thread(
                        self._execute,
                        "INSERT INTO scenic_config (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(value)),
                    )
            return await self.get_config()
        except Exception:
            logger.error("[ScenicRepo] 保存配置失败: %s", traceback.format_exc())
            return dict(_CONFIG_DEFAULTS)

    async def close(self) -> None:
        """清理资源（当前无连接池需要清理，预留接口）。"""
        pass
