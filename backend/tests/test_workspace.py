import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agentscope.message import TextBlock
from agentscope.model import ChatResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from agent.chat import reply_to_conversation
from agent.config import create_model
from database.models import Conversation, DigestRecord, Message, User
from database.store import init_schema
from main import create_app

TEST_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "workspace-test-secret",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    "SIGHT_PROVIDER": "deepseek",
    "SIGHT_MODEL": "deepseek-flash",
    "DEEPSEEK_API_KEY": "fake-test-key",
    "DASHSCOPE_API_KEY": "",
}
PASSWORD = "test-password-123"


def call(client, method, path, data=None):
    token = client.get("/api/auth/me").json["csrf_token"]
    return client.open(path, method=method, json=data, headers={"X-CSRF-Token": token})


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TEST_CONFIG)
        init_schema(self.app)
        self.addCleanup(self.app.extensions["sight_engine"].dispose)
        self.client = self.app.test_client()
        response = call(
            self.client, "POST", "/api/auth/register", {"username": "alice", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 201)
        self.user_id = response.json["user"]["id"]
        self.agent = self.client.get("/api/agents").json["agents"][0]

    def new_chat(self):
        response = call(self.client, "POST", "/api/conversations", {"agent_id": self.agent["id"]})
        self.assertEqual(response.status_code, 201)
        return response.json["conversation"]["id"]

    def test_password_hash_and_duplicate_username(self):
        with Session(self.app.extensions["sight_engine"]) as db:
            user = db.get(User, self.user_id)
            self.assertNotEqual(user.password_hash, PASSWORD)
            self.assertTrue(check_password_hash(user.password_hash, PASSWORD))
        response = call(
            self.client, "POST", "/api/auth/register", {"username": "ALICE", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("password", self.client.get("/api/auth/me").get_data(as_text=True))

    def test_login_logout_and_csrf_rotation(self):
        old_token = self.client.get("/api/auth/me").json["csrf_token"]
        self.assertEqual(call(self.client, "POST", "/api/auth/logout").status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/me").json["user"])
        bad = call(
            self.client, "POST", "/api/auth/login", {"username": "alice", "password": "wrong"}
        )
        self.assertEqual(bad.status_code, 401)
        good = call(
            self.client, "POST", "/api/auth/login", {"username": "alice", "password": PASSWORD}
        )
        self.assertEqual(good.status_code, 200)
        self.assertNotEqual(old_token, good.json["csrf_token"])
        self.assertEqual(
            self.client.post("/api/auth/logout", headers={"X-CSRF-Token": old_token}).status_code,
            403,
        )

    def test_private_endpoints_require_login(self):
        guest = self.app.test_client()
        for path in ("/api/agents", "/api/sources", "/api/conversations", "/api/digests"):
            with self.subTest(path=path):
                self.assertEqual(guest.get(path).status_code, 401)

    def test_mutations_require_csrf(self):
        for path in (
            "/api/agents",
            "/api/sources",
            "/api/conversations",
            "/api/auth/logout",
            "/api/digests",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json={"demo": True}).status_code, 403)

    def test_registration_validation(self):
        guest = self.app.test_client()
        for username, password in [
            ("aa", PASSWORD),
            ("invalid name", PASSWORD),
            ("valid", "short"),
            ("valid", 123),
        ]:
            response = call(
                guest, "POST", "/api/auth/register", {"username": username, "password": password}
            )
            self.assertEqual(response.status_code, 400)

    def test_agent_crud_and_snapshot(self):
        id = self.new_chat()
        update = {**self.agent, "name": "已更新助手", "system_prompt": "新的提示词"}
        self.assertEqual(
            call(self.client, "PUT", f"/api/agents/{self.agent['id']}", update).status_code, 200
        )
        detail = self.client.get(f"/api/conversations/{id}").json
        self.assertEqual(detail["conversation"]["agent_name"], self.agent["name"])
        with Session(self.app.extensions["sight_engine"]) as db:
            self.assertNotEqual(db.get(Conversation, id).system_prompt, "新的提示词")
        self.assertEqual(
            call(self.client, "DELETE", f"/api/agents/{self.agent['id']}").status_code, 204
        )
        detail = self.client.get(f"/api/conversations/{id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.json["conversation"]["agent_id"])

    def test_agent_validation(self):
        for body in (
            [],
            {},
            {**self.agent, "provider": "unknown"},
            {**self.agent, "system_prompt": " "},
        ):
            self.assertEqual(call(self.client, "POST", "/api/agents", body).status_code, 400)

    def test_source_normalization_and_duplicate(self):
        source = {"name": "我的订阅", "url": "https://example.com/feed#top"}
        response = call(self.client, "POST", "/api/sources", source)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["source"]["url"], "https://example.com/feed")
        self.assertEqual(call(self.client, "POST", "/api/sources", source).status_code, 409)
        self.assertEqual(
            call(
                self.client, "POST", "/api/sources", {"name": "bad", "url": "javascript:alert(1)"}
            ).status_code,
            400,
        )
        id = response.json["source"]["id"]
        self.assertEqual(call(self.client, "DELETE", f"/api/sources/{id}").status_code, 204)
        self.assertEqual(self.client.get("/api/sources").json["sources"], [])

    def test_digest_saved_for_user_and_guest_stays_stateless(self):
        response = call(
            self.client,
            "POST",
            "/api/digests",
            {"demo": True, "limit": 2, "agent_id": self.agent["id"]},
        )
        self.assertEqual(response.status_code, 200)
        id = response.json["id"]
        self.assertEqual(self.client.get(f"/api/digests/{id}").json, response.json)
        self.assertEqual(self.client.get("/api/digests").json["digests"][0]["count"], 2)
        guest = self.app.test_client().post("/api/digests", json={"demo": True})
        self.assertEqual(guest.status_code, 200)
        self.assertNotIn("id", guest.json)
        with Session(self.app.extensions["sight_engine"]) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(DigestRecord)), 1)

    def test_chat_saves_pair_and_replays_history(self):
        id = self.new_chat()
        mock = AsyncMock(return_value="这是助手的回复。")
        with patch("api.workspace.reply_to_conversation", mock):
            first = call(
                self.client, "POST", f"/api/conversations/{id}/messages", {"content": "第一问"}
            )
            second = call(
                self.client, "POST", f"/api/conversations/{id}/messages", {"content": "第二问"}
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(mock.call_args_list[0].args[2], [])
        self.assertEqual(
            [msg["role"] for msg in mock.call_args_list[1].args[2]], ["user", "assistant"]
        )
        self.assertEqual(len(self.client.get(f"/api/conversations/{id}").json["messages"]), 4)
        self.assertEqual(
            self.client.get("/api/conversations").json["conversations"][0]["title"], "第一问"
        )

    def test_chat_failure_does_not_save_partial_turn(self):
        id = self.new_chat()
        with patch(
            "api.workspace.reply_to_conversation",
            new=AsyncMock(side_effect=RuntimeError("secret response")),
        ):
            response = call(
                self.client, "POST", f"/api/conversations/{id}/messages", {"content": "你好"}
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret response", response.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/api/conversations/{id}").json["messages"], [])

    def test_chat_requires_provider_key(self):
        self.app.config["DEEPSEEK_API_KEY"] = ""
        id = self.new_chat()
        response = call(
            self.client, "POST", f"/api/conversations/{id}/messages", {"content": "你好"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get(f"/api/conversations/{id}").json["messages"], [])

    def test_concurrent_chat_change_is_rejected(self):
        id = self.new_chat()

        async def another_turn(*args):
            with Session(self.app.extensions["sight_engine"]) as db:
                db.get(Conversation, id).revision = 2
                db.add_all(
                    [
                        Message(conversation_id=id, position=1, role="user", content="另一问"),
                        Message(conversation_id=id, position=2, role="assistant", content="另一答"),
                    ]
                )
                db.commit()
            return "迟到的回复"

        with patch("api.workspace.reply_to_conversation", side_effect=another_turn):
            response = call(
                self.client, "POST", f"/api/conversations/{id}/messages", {"content": "你好"}
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.client.get(f"/api/conversations/{id}").json["messages"]), 2)

    def test_conversation_delete_cascades_messages(self):
        id = self.new_chat()
        with patch("api.workspace.reply_to_conversation", new=AsyncMock(return_value="你好")):
            call(self.client, "POST", f"/api/conversations/{id}/messages", {"content": "你好"})
        self.assertEqual(call(self.client, "DELETE", f"/api/conversations/{id}").status_code, 204)
        with Session(self.app.extensions["sight_engine"]) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 0)

    def test_user_isolation_for_all_records(self):
        chat_id = self.new_chat()
        source = call(
            self.client,
            "POST",
            "/api/sources",
            {"name": "私有源", "url": "https://example.com/feed"},
        ).json["source"]
        digest = call(self.client, "POST", "/api/digests", {"demo": True}).json
        bob = self.app.test_client()
        call(bob, "POST", "/api/auth/register", {"username": "bob", "password": PASSWORD})
        for path in (f"/api/conversations/{chat_id}", f"/api/digests/{digest['id']}"):
            self.assertEqual(bob.get(path).status_code, 404)
        for path in (
            f"/api/agents/{self.agent['id']}",
            f"/api/conversations/{chat_id}",
            f"/api/sources/{source['id']}",
            f"/api/digests/{digest['id']}",
        ):
            self.assertEqual(call(bob, "DELETE", path).status_code, 404)
        self.assertEqual(
            call(bob, "POST", "/api/conversations", {"agent_id": self.agent["id"]}).status_code, 404
        )
        self.assertEqual(
            call(
                bob, "POST", "/api/digests", {"demo": True, "agent_id": self.agent["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(bob.get("/api/sources").json["sources"], [])
        self.assertEqual(bob.get("/api/digests").json["digests"], [])

    def test_repeated_init_preserves_data(self):
        init_schema(self.app)
        self.assertEqual(self.client.get("/api/agents").json["agents"][0]["id"], self.agent["id"])

    def test_data_survives_new_app_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = {
                **TEST_CONFIG,
                "DATABASE_URL": f"sqlite+pysqlite:///{Path(directory) / 'sight.db'}",
            }
            first = create_app(settings)
            init_schema(first)
            client = first.test_client()
            call(
                client,
                "POST",
                "/api/auth/register",
                {"username": "persisted", "password": PASSWORD},
            )
            call(
                client,
                "POST",
                "/api/sources",
                {"name": "持久订阅", "url": "https://example.com/feed"},
            )
            call(client, "POST", "/api/digests", {"demo": True})
            first.extensions["sight_engine"].dispose()
            second = create_app(settings)
            try:
                client = second.test_client()
                response = call(
                    client,
                    "POST",
                    "/api/auth/login",
                    {"username": "persisted", "password": PASSWORD},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(client.get("/api/sources").json["sources"]), 1)
                self.assertEqual(len(client.get("/api/digests").json["digests"]), 1)
            finally:
                second.extensions["sight_engine"].dispose()


class ChatAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_agentscope_text_reply(self):
        model = create_model(TEST_CONFIG)
        response = ChatResponse(content=[TextBlock(text="你好，我是资讯助手。")], is_last=True)
        with (
            patch("agent.chat.create_model", return_value=model),
            patch.object(model, "_call_api", new=AsyncMock(return_value=response)),
        ):
            result = await reply_to_conversation(
                TEST_CONFIG,
                {
                    "provider": "deepseek",
                    "model": "deepseek-flash",
                    "system_prompt": "请用中文回答",
                },
                [],
                "你好",
            )
        self.assertEqual(result, "你好，我是资讯助手。")
