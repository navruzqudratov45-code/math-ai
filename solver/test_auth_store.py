import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import auth_store


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        auth_store.DB_PATH = Path(self.temp.name) / "test.sqlite"
        self.password = "test-password-123"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, **values):
        return auth_store.op(values)

    def register(self, email="learner@example.test"):
        return self.call(op="register", name="Test Learner", email=email, password=self.password, role="admin", plan="premium")

    def test_register_hashes_password_and_never_assigns_public_admin_role(self):
        user = self.register()
        self.assertEqual(user["role"], "user")
        db = auth_store.connect()
        row = db.execute("SELECT password_hash,password_salt FROM users WHERE id=?", (user["id"],)).fetchone()
        db.close()
        self.assertNotEqual(row["password_hash"], self.password)
        self.assertNotEqual(row["password_hash"], row["password_salt"])

    def test_owner_registration_automatically_grants_admin_and_other_admin_promotion_is_denied(self):
        owner = self.call(op="register", name="Platform Owner", email="NAVRUZQUDRATOV45@GMAIL.COM", password=self.password)
        self.assertEqual((owner["role"], owner["status"]), ("admin", "active"))
        learner = self.register("ordinary@example.test")
        with self.assertRaises(ValueError):
            self.call(op="admin_user", actorId=owner["id"], targetId=learner["id"], role="admin")

    def test_login_and_session_expiry_and_logout(self):
        user = self.register()
        session = {"op": "login", "email": user["email"], "password": self.password, "tokenHash": "token-hash", "expiresAt": auth_store.now()+100}
        self.assertEqual(self.call(**session)["id"], user["id"])
        self.assertEqual(self.call(op="session", tokenHash="token-hash")["id"], user["id"])
        self.call(op="logout", tokenHash="token-hash")
        self.assertIsNone(self.call(op="session", tokenHash="token-hash"))
        self.call(op="register_session", userId=user["id"], tokenHash="expired", expiresAt=auth_store.now()-1)
        self.assertIsNone(self.call(op="session", tokenHash="expired"))

    def test_password_reset_token_is_one_time_and_revokes_sessions(self):
        user = self.register()
        self.call(op="register_session", userId=user["id"], tokenHash="active-session", expiresAt=auth_store.now()+1000)
        self.call(op="create_reset", email=user["email"], tokenHash="reset-hash", expiresAt=auth_store.now()+1000)
        self.call(op="reset_password", tokenHash="reset-hash", password="another-secure-password")
        with self.assertRaises(PermissionError):
            self.call(op="reset_password", tokenHash="reset-hash", password="another-secure-password")
        self.assertIsNone(self.call(op="session", tokenHash="active-session"))

    def test_problem_history_is_user_scoped_and_saved_status_can_toggle(self):
        first = self.register()
        second = self.register("second@example.test")
        problem_id = self.call(op="save_problem", userId=first["id"], prompt="x^2", answer="x=2", domain="math")
        self.assertEqual(self.call(op="history", userId=first["id"])["total"], 1)
        self.assertEqual(self.call(op="history", userId=second["id"])["total"], 0)
        self.assertFalse(self.call(op="toggle_saved", userId=second["id"], problemId=problem_id)["ok"])
        self.assertTrue(self.call(op="toggle_saved", userId=first["id"], problemId=problem_id)["ok"])
        self.assertTrue(self.call(op="history", userId=first["id"])["items"][0]["saved"])

    def test_saved_problem_capacity_is_not_restricted_by_plan(self):
        user = self.register()
        self.call(op="settings", values={"freeSavedCapacity": 1, "premiumSavedCapacity": 4})
        first = self.call(op="save_problem", userId=user["id"], prompt="A", answer="1")
        second = self.call(op="save_problem", userId=user["id"], prompt="B", answer="2")
        self.assertTrue(self.call(op="toggle_saved", userId=user["id"], problemId=first)["ok"])
        blocked = self.call(op="toggle_saved", userId=user["id"], problemId=second)
        self.assertEqual(blocked["reason"], "capacity")
        self.call(op="provision_admin", email="navruzqudratov45@gmail.com", name="Admin", password="long-admin-password-123")
        admin = self.call(op="login", email="navruzqudratov45@gmail.com", password="long-admin-password-123", tokenHash="admin-session", expiresAt=auth_store.now()+1000)
        self.call(op="admin_user", actorId=admin["id"], targetId=user["id"], plan="premium")
        self.assertEqual(self.call(op="usage", userId=user["id"])["savedCapacity"], 1)
        self.assertEqual(self.call(op="toggle_saved", userId=user["id"], problemId=second)["reason"], "capacity")

    def test_user_cannot_set_role_and_admin_controls_user_and_plan(self):
        learner = self.register()
        admin = self.call(op="provision_admin", email="navruzqudratov45@gmail.com", name="Admin User", password="long-admin-password-123")
        self.assertTrue(admin)
        admin_user = self.call(op="login", email="navruzqudratov45@gmail.com", password="long-admin-password-123", tokenHash="admin-session", expiresAt=auth_store.now()+1000)
        self.assertEqual(admin_user["role"], "admin")
        changed = self.call(op="admin_user", actorId=admin_user["id"], targetId=learner["id"], role="user", plan="premium", status="active")
        self.assertEqual(changed["plan"], "premium")
        with self.assertRaises(ValueError):
            self.call(op="admin_user", actorId=admin_user["id"], targetId=admin_user["id"], role="user")

    def test_platform_config_and_request_statistics(self):
        user = self.register()
        self.call(op="settings", values={"freeDailyLimit": 4, "registrationEnabled": False})
        self.call(op="log_request", userId=user["id"], model="test-model", domain="geometry", status=200, latencyMs=100)
        settings = self.call(op="settings")
        stats = self.call(op="admin_stats")
        self.assertEqual(settings["freeDailyLimit"], 4)
        self.assertFalse(settings["registrationEnabled"])
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(self.call(op="usage", userId=user["id"])["limit"], 4)

    def test_free_daily_limit_counts_text_and_image_then_blocks(self):
        user = self.register()
        outcomes = [self.call(op="reserve_usage", userId=user["id"], hasText=i < 99, hasImage=i == 99) for i in range(100)]
        denied = self.call(op="reserve_usage", userId=user["id"], hasText=True, hasImage=False)
        usage = self.call(op="usage", userId=user["id"])
        self.assertTrue(all(result["allowed"] for result in outcomes))
        self.assertEqual({result["limit"] for result in outcomes}, {100})
        self.assertFalse(denied["allowed"])
        self.assertEqual((usage["used"], usage["remaining"]), (100, 0))
        self.assertEqual((usage["textRequests"], usage["imageRequests"]), (99, 1))
        self.assertTrue(usage["premiumExtendedExplanations"])
        self.assertTrue(usage["premiumPriorityRouting"])
        self.assertEqual(user["role"], "user")
        self.assertEqual(user["plan"], "free")

    def test_daily_usage_resets_at_utc_date_boundary(self):
        user = self.register()
        with patch.object(auth_store, "utc_date", side_effect=["2026-11-05", "2026-11-06", "2026-11-06"]):
            first = self.call(op="reserve_usage", userId=user["id"], hasText=True)
            next_day = self.call(op="reserve_usage", userId=user["id"], hasImage=True)
            usage = self.call(op="usage", userId=user["id"])
        self.assertEqual(first["used"], 1)
        self.assertEqual(next_day["used"], 1)
        self.assertEqual(usage["usageDate"], "2026-11-06")
        self.assertEqual(usage["used"], 1)
        self.assertEqual(usage["imageRequests"], 1)

    def test_premium_and_free_users_receive_the_same_daily_allowance(self):
        learner = self.register()
        self.call(op="provision_admin", email="navruzqudratov45@gmail.com", name="Admin", password="long-admin-password-123")
        admin = self.call(op="login", email="navruzqudratov45@gmail.com", password="long-admin-password-123", tokenHash="admin-session", expiresAt=auth_store.now()+1000)
        premium = self.call(op="admin_user", actorId=admin["id"], targetId=learner["id"], plan="premium")
        self.assertEqual((premium["plan"], premium["subscriptionStatus"], premium["subscriptionSource"]), ("premium", "active", "admin"))
        granted = [self.call(op="reserve_usage", userId=learner["id"], hasText=True) for _ in range(100)]
        denied = self.call(op="reserve_usage", userId=learner["id"], hasImage=True)
        self.assertTrue(all(item["allowed"] for item in granted))
        self.assertEqual(granted[-1]["limit"], 100)
        self.assertFalse(denied["allowed"])
        self.call(op="admin_user", actorId=admin["id"], targetId=learner["id"], subscriptionStatus="suspended")
        self.assertEqual(self.call(op="usage", userId=learner["id"])["plan"], "free")
        self.assertEqual(self.call(op="usage", userId=learner["id"])["limit"], 100)

    def test_parallel_free_requests_cannot_exceed_atomic_limit(self):
        user = self.register()
        def reserve(_):
            return self.call(op="reserve_usage", userId=user["id"], hasText=True)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(reserve, range(112)))
        self.assertEqual(sum(result["allowed"] for result in results), 100)
        self.assertEqual(self.call(op="usage", userId=user["id"])["used"], 100)

    def test_existing_phase_five_database_is_migrated_and_usage_backfilled(self):
        import sqlite3
        db = sqlite3.connect(auth_store.DB_PATH)
        db.executescript("""
          CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,name TEXT,password_hash TEXT,password_salt TEXT,role TEXT DEFAULT 'user',plan TEXT DEFAULT 'premium',status TEXT DEFAULT 'active',created_at INTEGER,updated_at INTEGER);
          CREATE TABLE ai_requests(id INTEGER PRIMARY KEY,user_id INTEGER,model TEXT,domain TEXT,status INTEGER,latency_ms INTEGER,error_code TEXT,created_at INTEGER);
          CREATE TABLE platform_settings(key TEXT PRIMARY KEY,value TEXT,updated_at INTEGER);
        """)
        stamp = auth_store.now()
        db.execute("INSERT INTO users VALUES(1,'legacy@example.test','Legacy','hash','salt','user','premium','active',?,?)", (stamp, stamp))
        db.execute("INSERT INTO ai_requests VALUES(1,1,'test','math',500,10,'provider_error',?)", (stamp,))
        db.commit(); db.close()
        migrated = auth_store.connect()
        user = migrated.execute("SELECT subscription_status,subscription_source FROM users WHERE id=1").fetchone()
        usage = migrated.execute("SELECT request_count,text_count,image_count FROM daily_usage WHERE user_id=1").fetchone()
        subscription = migrated.execute("SELECT provider,status FROM subscriptions WHERE user_id=1").fetchone()
        migrated.close()
        self.assertEqual(tuple(user), ("active", "admin"))
        self.assertEqual(tuple(usage), (1, 1, 0))
        self.assertEqual(tuple(subscription), ("admin", "active"))

    def payment_order(self, user, provider="payme", plan="premium_monthly", key="stable-idem"):
        return self.call(op="payment_create_order", id=f"order-{key}", idempotencyKey=key, userId=user["id"], provider=provider,
                         planCode=plan, amountUZS=12000 if plan == "premium_monthly" else 100000)

    def test_payme_success_duplicate_and_failed_amount_callbacks_are_safe(self):
        user = self.register()
        order = self.payment_order(user)
        self.assertEqual(self.call(op="payment_create_order", id="ignored", idempotencyKey="stable-idem", userId=user["id"], provider="payme", planCode="premium_monthly", amountUZS=12000)["id"], order["id"])
        checked = self.call(op="payment_check_order", id=order["id"], provider="payme")
        self.assertEqual(checked["amountMinor"], 1_200_000)
        self.assertNotEqual(checked["amountMinor"], 1_200_001)
        tx = self.call(op="payment_payme_create", orderId=order["id"], transactionId="payme-tx-1", providerTime=auth_store.now()*1000, amountMinor=1_200_000)
        duplicate = self.call(op="payment_payme_create", orderId=order["id"], transactionId="payme-tx-1", providerTime=auth_store.now()*1000, amountMinor=1_200_000)
        self.assertTrue(tx["ok"] and duplicate["ok"] and duplicate["duplicate"])
        performed = self.call(op="payment_payme_perform", transactionId="payme-tx-1")
        repeated = self.call(op="payment_payme_perform", transactionId="payme-tx-1")
        self.assertTrue(performed["ok"] and repeated["ok"] and repeated["duplicate"])
        current = self.call(op="session", tokenHash="missing")
        db = auth_store.connect(); saved_user = db.execute("SELECT plan,subscription_source,subscription_ends_at FROM users WHERE id=?", (user["id"],)).fetchone(); db.close()
        self.assertIsNone(current)
        self.assertEqual(saved_user["plan"], "premium")
        self.assertEqual(saved_user["subscription_source"], "payment")
        self.assertGreater(saved_user["subscription_ends_at"], auth_store.now())

    def test_click_prepare_complete_duplicate_and_wrong_amount(self):
        user = self.register()
        order = self.payment_order(user, provider="click", key="click-success")
        wrong = self.call(op="payment_click_prepare", orderId=order["id"], transactionId="click-wrong", paymentId="doc-wrong", amountUZS=11999, amountMinor=1_199_900)
        self.assertFalse(wrong["ok"])
        prep = self.call(op="payment_click_prepare", orderId=order["id"], transactionId="click-tx", paymentId="click-doc", amountUZS=12000, amountMinor=1_200_000)
        self.assertTrue(prep["ok"])
        completed = self.call(op="payment_click_complete", orderId=order["id"], transactionId="click-tx", prepareId=prep["prepareId"], amountUZS=12000, amountMinor=1_200_000, providerError=0)
        duplicate = self.call(op="payment_click_complete", orderId=order["id"], transactionId="click-tx", prepareId=prep["prepareId"], amountUZS=12000, amountMinor=1_200_000, providerError=0)
        self.assertTrue(completed["ok"] and duplicate["ok"] and duplicate["duplicate"])
        db = auth_store.connect(); status = db.execute("SELECT status FROM payment_orders WHERE id=?", (order["id"],)).fetchone()[0]; payment_id = db.execute("SELECT provider_payment_id FROM payment_transactions WHERE order_id=?", (order["id"],)).fetchone()[0]; db.close()
        self.assertEqual(status, "paid")
        self.assertEqual(payment_id, "click-doc")

    def test_provider_failure_duplicate_and_subscription_expiration(self):
        user = self.register()
        order = self.payment_order(user, provider="click", key="click-fail")
        prep = self.call(op="payment_click_prepare", orderId=order["id"], transactionId="click-fail-tx", paymentId="click-fail-doc", amountUZS=12000, amountMinor=1_200_000)
        failed = self.call(op="payment_click_complete", orderId=order["id"], transactionId="click-fail-tx", prepareId=prep["prepareId"], amountUZS=12000, amountMinor=1_200_000, providerError=-1)
        repeated = self.call(op="payment_click_complete", orderId=order["id"], transactionId="click-fail-tx", prepareId=prep["prepareId"], amountUZS=12000, amountMinor=1_200_000, providerError=-1)
        self.assertTrue(failed["ok"] and repeated["ok"])
        self.assertTrue(repeated["duplicate"])
        self.assertEqual(repeated, {"ok": True, "canceled": True, "duplicate": True})
        late_success = self.call(op="payment_click_complete", orderId=order["id"], transactionId="click-fail-tx", prepareId=prep["prepareId"], amountUZS=12000, amountMinor=1_200_000, providerError=0)
        self.assertEqual(late_success, {"ok": False, "reason": "canceled"})
        self.assertEqual(self.call(op="usage", userId=user["id"])["plan"], "free")

        paid = self.payment_order(user, provider="payme", key="expiring")
        self.call(op="payment_payme_create", orderId=paid["id"], transactionId="payme-expire-tx", providerTime=auth_store.now()*1000, amountMinor=1_200_000)
        self.call(op="payment_payme_perform", transactionId="payme-expire-tx")
        db = auth_store.connect(); db.execute("UPDATE users SET subscription_ends_at=? WHERE id=?", (auth_store.now()-1, user["id"])); db.execute("UPDATE subscriptions SET period_end=? WHERE user_id=? AND provider='payme' AND status='active'", (auth_store.now()-1, user["id"])); db.commit(); db.close()
        db = auth_store.connect(); expired = db.execute("SELECT plan,subscription_status,subscription_source FROM users WHERE id=?", (user["id"],)).fetchone(); db.close()
        self.assertEqual(tuple(expired), ("free", "expired", "none"))

    def test_supervisor_audit_purges_expired_sessions_and_reset_tokens(self):
        user = self.register()
        self.call(op="register_session", userId=user["id"], tokenHash="expired-supervisor-session", expiresAt=auth_store.now()-5)
        self.call(op="create_reset", email=user["email"], tokenHash="expired-supervisor-reset", expiresAt=auth_store.now()-5)
        report = self.call(op="supervisor_audit", runAutoFix=True)
        self.assertEqual(report["remediations"]["expiredSessionsPurged"], 1)
        self.assertEqual(report["remediations"]["expiredResetTokensPurged"], 1)
        db = auth_store.connect(); sessions = db.execute("SELECT COUNT(*) FROM sessions WHERE token_hash='expired-supervisor-session'").fetchone()[0]; tokens = db.execute("SELECT COUNT(*) FROM reset_tokens WHERE token_hash='expired-supervisor-reset'").fetchone()[0]; db.close()
        self.assertEqual((sessions, tokens), (0, 0))
        self.assertTrue(any(event["autoFixed"] and event["module"] == "auth" for event in report["events"]))

    def test_supervisor_audit_repairs_subscriptions_and_corrupt_settings(self):
        expired_user = self.register("expired-premium@example.test")
        active_user = self.register("active-paid@example.test")
        stamp = auth_store.now()
        db = auth_store.connect()
        db.execute("UPDATE users SET plan='premium',subscription_status='active',subscription_source='payment',subscription_ends_at=? WHERE id=?", (stamp-1, expired_user["id"]))
        db.execute("INSERT INTO subscriptions(user_id,plan_code,provider,status,period_start,period_end,created_at,updated_at) VALUES(?,'premium_monthly','payme','active',?,?,?,?)", (expired_user["id"],stamp-100,stamp-1,stamp-100,stamp-100))
        db.execute("INSERT INTO subscriptions(user_id,plan_code,provider,status,period_start,period_end,created_at,updated_at) VALUES(?,'premium_monthly','click','active',?,?,?,?)", (active_user["id"],stamp,stamp+86400,stamp,stamp))
        db.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES('freeDailyLimit','10001',?) ON CONFLICT(key) DO UPDATE SET value='10001',updated_at=excluded.updated_at", (stamp,))
        db.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES('premiumSavedCapacity','-4',?) ON CONFLICT(key) DO UPDATE SET value='-4',updated_at=excluded.updated_at", (stamp,))
        db.commit(); db.close()
        report = self.call(op="supervisor_audit", runAutoFix=True)
        self.assertGreaterEqual(report["remediations"]["subscriptionsReconciled"], 3)
        self.assertEqual(report["remediations"]["corruptSettingsFixed"], 2)
        db = auth_store.connect(); expired = db.execute("SELECT plan,subscription_status,subscription_source FROM users WHERE id=?", (expired_user["id"],)).fetchone(); active = db.execute("SELECT plan,subscription_status,subscription_source FROM users WHERE id=?", (active_user["id"],)).fetchone(); settings = dict(db.execute("SELECT key,value FROM platform_settings WHERE key IN ('freeDailyLimit','premiumSavedCapacity')").fetchall()); db.close()
        self.assertEqual(tuple(expired), ("free", "expired", "none"))
        self.assertEqual(tuple(active), ("premium", "active", "payment"))
        self.assertEqual(settings, {"freeDailyLimit": "100", "premiumSavedCapacity": "1000"})

    def test_supervisor_log_records_ai_mismatch_and_is_returned(self):
        self.assertTrue(self.call(op="supervisor_log", module="sympy", severity="warning", code="ai_sympy_result_mismatch", message="Natijalar mos kelmadi.", remediation="Hisobni tekshiring."))
        self.assertTrue(self.call(op="supervisor_log", module="openrouter", severity="critical", code="openrouter_upstream_5xx", message="Upstream xatosi."))
        report = self.call(op="supervisor_audit", runAutoFix=False)
        logged = {event["code"] for event in report["events"]}
        self.assertIn("ai_sympy_result_mismatch", logged)
        self.assertIn("openrouter_upstream_5xx", logged)

    def test_free_allowance_defaults_migrate_existing_saved_defaults(self):
        db = auth_store.connect()
        db.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES('freeDailyLimit','5',?) ON CONFLICT(key) DO UPDATE SET value='5',updated_at=excluded.updated_at", (auth_store.now(),))
        db.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES('freeSavedCapacity','10',?) ON CONFLICT(key) DO UPDATE SET value='10',updated_at=excluded.updated_at", (auth_store.now(),))
        db.execute("PRAGMA user_version=3"); db.commit(); db.close()
        settings = self.call(op="settings")
        self.assertEqual(settings["freeDailyLimit"], 100)
        self.assertEqual(settings["freeSavedCapacity"], 1000)


if __name__ == "__main__":
    unittest.main()
