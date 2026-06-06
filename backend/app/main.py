import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent_tools import CustomerContext
from .config import APP_NAME, FRONTEND_DIR, load_env_file
from .database import connect, init_db, now_iso, row_to_dict
from .workflow import SalesAgentWorkflow, TASK_LABELS, to_json


class TaskRequest(BaseModel):
    task_type: str


class TaskActionRequest(BaseModel):
    action: str


class CustomerCreateRequest(BaseModel):
    name: str
    phone: str
    level: str = "B"
    notes: str = ""


class InteractionCreateRequest(BaseModel):
    channel: str = "wechat"
    content: str
    metadata: dict = {}


app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
workflow = SalesAgentWorkflow()


@app.on_event("startup")
def startup() -> None:
    load_env_file()
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME, "tasks": TASK_LABELS}


@app.get("/api/customers")
def list_customers() -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM customers ORDER BY level DESC, id ASC").fetchall()
    return {"customers": [row_to_dict(row) for row in rows]}


@app.post("/api/customers")
def create_customer(request: CustomerCreateRequest) -> dict:
    if not request.name.strip() or not request.phone.strip():
        raise HTTPException(status_code=400, detail="Customer name and phone are required.")
    created = now_iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO customers (name, phone, level, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.name.strip(),
                request.phone.strip(),
                request.level.strip().upper() or "B",
                request.notes.strip(),
                created,
                created,
            ),
        )
    return {"customer": load_customer(cursor.lastrowid)}


@app.get("/api/customers/{customer_id}")
def customer_detail(customer_id: int) -> dict:
    return {"customer": load_customer(customer_id), "tasks": load_tasks(customer_id)}


@app.post("/api/customers/{customer_id}/interactions")
def create_interaction(customer_id: int, request: InteractionCreateRequest) -> dict:
    load_customer(customer_id)
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Interaction content cannot be empty.")
    created = now_iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO interactions (customer_id, channel, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                request.channel.strip() or "manual",
                request.content.strip(),
                json.dumps(request.metadata, ensure_ascii=False),
                created,
            ),
        )
    with connect() as conn:
        row = conn.execute("SELECT * FROM interactions WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return {"interaction": row_to_dict(row)}


@app.post("/api/customers/{customer_id}/tasks")
def run_task(customer_id: int, request: TaskRequest) -> dict:
    if request.task_type not in TASK_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported task type.")

    ctx = build_context(customer_id)
    state = workflow.run(ctx, request.task_type)
    created = now_iso()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_tasks
            (customer_id, task_type, status, result, reasoning, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                customer_id,
                request.task_type,
                to_json(state["result"]),
                state["reasoning"],
                created,
                created,
            ),
        )
        task_id = cursor.lastrowid
    task = get_task(task_id)
    task["steps"] = state["steps"]
    return {"task": task}


@app.post("/api/tasks/{task_id}/action")
def act_on_task(task_id: int, request: TaskActionRequest) -> dict:
    action = request.action
    if action not in {"confirm", "abandon", "regenerate"}:
        raise HTTPException(status_code=400, detail="Action must be confirm, abandon or regenerate.")

    task = get_task(task_id)
    if action == "abandon":
        update_task_status(task_id, "abandoned")
        return {"task": get_task(task_id), "message": "已放弃本次建议。"}

    if action == "regenerate":
        ctx = build_context(task["customer_id"])
        state = workflow.run(ctx, task["task_type"], variant=1)
        updated = now_iso()
        with connect() as conn:
            conn.execute(
                "UPDATE agent_tasks SET status = 'pending', result = ?, reasoning = ?, updated_at = ? WHERE id = ?",
                (to_json(state["result"]), state["reasoning"], updated, task_id),
            )
        refreshed = get_task(task_id)
        refreshed["steps"] = state["steps"]
        return {"task": refreshed, "message": "已重新生成建议。"}

    apply_task_result(task)
    update_task_status(task_id, "confirmed")
    return {"task": get_task(task_id), "message": "已确认并写入客户记忆。"}


@app.get("/api/tasks")
def list_tasks() -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT agent_tasks.*, customers.name AS customer_name
            FROM agent_tasks
            JOIN customers ON customers.id = agent_tasks.customer_id
            ORDER BY agent_tasks.id DESC
            LIMIT 30
            """
        ).fetchall()
    return {"tasks": [row_to_dict(row) for row in rows]}


@app.get("/api/customers/{customer_id}/export")
def export_customer(customer_id: int) -> dict:
    customer = load_customer(customer_id)
    tasks = load_tasks(customer_id)
    return {
        "customer": customer,
        "tasks": tasks,
        "exported_at": now_iso(),
        "usage": "可用于 CRM 客户档案迁移、销售主管复盘或智能体记忆审计。",
    }


def load_customer(customer_id: int) -> dict:
    with connect() as conn:
        customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
        interactions = conn.execute(
            "SELECT * FROM interactions WHERE customer_id = ? ORDER BY id DESC",
            (customer_id,),
        ).fetchall()
    data = row_to_dict(customer)
    data["interactions"] = [row_to_dict(row) for row in interactions]
    return data


def load_tasks(customer_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_tasks WHERE customer_id = ? ORDER BY id DESC LIMIT 20",
            (customer_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_task(task_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found.")
    return row_to_dict(row)


def update_task_status(task_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE agent_tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), task_id))


def build_context(customer_id: int) -> CustomerContext:
    customer = load_customer(customer_id)
    return CustomerContext(
        id=customer["id"],
        name=customer["name"],
        level=customer["level"],
        notes=customer["notes"],
        profile=customer.get("profile") or {},
        tags=customer.get("tags") or [],
        interactions=[item["content"] for item in customer["interactions"]],
    )


def apply_task_result(task: dict) -> None:
    result = task["result"]
    customer_id = task["customer_id"]
    task_type = task["task_type"]
    updated = now_iso()

    with connect() as conn:
        if task_type == "profile":
            conn.execute(
                "UPDATE customers SET profile = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result, ensure_ascii=False), updated, customer_id),
            )
        elif task_type == "tags":
            conn.execute(
                "UPDATE customers SET tags = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result, ensure_ascii=False), updated, customer_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO interactions (customer_id, channel, content, metadata, created_at)
                VALUES (?, 'agent', ?, ?, ?)
                """,
                (
                    customer_id,
                    f"已确认{TASK_LABELS[task_type]}：{json.dumps(result, ensure_ascii=False)}",
                    json.dumps({"task_id": task["id"], "task_type": task_type}, ensure_ascii=False),
                    updated,
                ),
            )


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
