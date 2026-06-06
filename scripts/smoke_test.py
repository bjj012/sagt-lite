from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

db_path = ROOT / "data" / "sagt.sqlite3"
db_path.unlink(missing_ok=True)

from fastapi.testclient import TestClient

from backend.app.main import app


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text

        customers = client.get("/api/customers")
        assert customers.status_code == 200, customers.text
        customer = customers.json()["customers"][0]
        customer_id = customer["id"]

        created = client.post(
            "/api/customers",
            json={"name": "赵经理", "phone": "13900000000", "level": "A", "notes": "企业客户，关注交付稳定性。"},
        )
        assert created.status_code == 200, created.text
        created_id = created.json()["customer"]["id"]

        interaction = client.post(
            f"/api/customers/{created_id}/interactions",
            json={"channel": "wechat", "content": "客户要求下周三前给出年会伴手礼方案，并确认发票信息。"},
        )
        assert interaction.status_code == 200, interaction.text

        profile_task = client.post(
            f"/api/customers/{customer_id}/tasks",
            json={"task_type": "profile"},
        )
        assert profile_task.status_code == 200, profile_task.text
        task = profile_task.json()["task"]
        assert task["status"] == "pending"
        assert task["result"]["姓名"]

        confirm = client.post(f"/api/tasks/{task['id']}/action", json={"action": "confirm"})
        assert confirm.status_code == 200, confirm.text
        assert confirm.json()["task"]["status"] == "confirmed"

        tag_task = client.post(
            f"/api/customers/{customer_id}/tasks",
            json={"task_type": "tags"},
        )
        assert tag_task.status_code == 200, tag_task.text
        tag_id = tag_task.json()["task"]["id"]
        regen = client.post(f"/api/tasks/{tag_id}/action", json={"action": "regenerate"})
        assert regen.status_code == 200, regen.text
        assert "需二次确认" in regen.json()["task"]["result"]

        detail = client.get(f"/api/customers/{customer_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["customer"]["profile"]["姓名"] == customer["name"]

        exported = client.get(f"/api/customers/{customer_id}/export")
        assert exported.status_code == 200, exported.text
        assert exported.json()["customer"]["id"] == customer_id

        print("Sagt Lite smoke test passed.")
        print(f"customer_id={customer_id}, profile_task={task['id']}, tag_task={tag_id}")


if __name__ == "__main__":
    main()
