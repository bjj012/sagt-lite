import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import DB_PATH


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    data = {key: row[key] for key in row.keys()}
    for key in ("profile", "tags", "metadata", "result", "messages"):
        if key in data and isinstance(data[key], str) and data[key]:
            try:
                data[key] = json.loads(data[key])
            except json.JSONDecodeError:
                pass
    return data


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                level TEXT NOT NULL,
                profile TEXT NOT NULL DEFAULT '{}',
                tags TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS agent_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS total FROM customers").fetchone()["total"]
        if count == 0:
            seed_data(conn)


def seed_data(conn: sqlite3.Connection) -> None:
    created = now_iso()
    customers = [
        (
            "程哥",
            "13800010001",
            "A",
            "老客户，注重面子和接待品质，偏好茅台、红酒和家庭聚会场景。",
            [
                "客户说：明天上午10点有商务宴请，想准备几瓶拿得出手的酒。",
                "客户曾购买飞天茅台、五粮液和红酒礼盒，预算通常在500元到1200元之间。",
                "客户提到儿子喜欢篮球，父亲喜欢收藏老酒，家庭聚会频率高。",
                "上次售后反馈：希望提前一天提醒发货进度，不喜欢临时通知。",
            ],
        ),
        (
            "李女士",
            "13800010002",
            "B",
            "新晋会员，关注性价比和售后体验，对节日礼盒敏感。",
            [
                "客户咨询端午礼盒，明确说预算在300元以内，希望包装显得高级。",
                "客户担心物流破损，希望客服确认发货保护措施。",
                "客户喜欢少糖茶点和低度果酒，不喜欢过度推销。",
            ],
        ),
        (
            "王总",
            "13800010003",
            "S",
            "企业大客户，采购频次高，关注稳定供应、发票和定制服务。",
            [
                "客户计划为年会采购白酒和伴手礼，预算较高，需要对公发票。",
                "客户多次强调交付时间，要求销售给出明确排期。",
                "客户接受定制瓶身祝福语，但需要先看样稿。",
            ],
        ),
    ]

    for name, phone, level, notes, messages in customers:
        cursor = conn.execute(
            """
            INSERT INTO customers (name, phone, level, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, phone, level, notes, created, created),
        )
        customer_id = cursor.lastrowid
        for message in messages:
            conn.execute(
                """
                INSERT INTO interactions (customer_id, channel, content, metadata, created_at)
                VALUES (?, 'wechat', ?, '{}', ?)
                """,
                (customer_id, message, created),
            )
