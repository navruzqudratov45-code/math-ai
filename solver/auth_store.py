"""Small SQLite persistence layer for MathAI authentication and account data."""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(os.environ.get("MATHAI_DB_PATH", Path.cwd() / "data" / "mathai.sqlite"))
OWNER_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "navruzqudratov45@gmail.com").strip().lower()
SCHEMA_VERSION = 4


def connect(run_maintenance: bool = True) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        db.execute("PRAGMA journal_mode = WAL")
    schema_version = db.execute("PRAGMA user_version").fetchone()[0]
    if schema_version < SCHEMA_VERSION:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
            plan TEXT NOT NULL DEFAULT 'free' CHECK(plan IN ('free','premium')),
            subscription_status TEXT NOT NULL DEFAULT 'free' CHECK(subscription_status IN ('free','active','suspended','expired')),
            subscription_source TEXT NOT NULL DEFAULT 'none' CHECK(subscription_source IN ('none','admin','payment')),
            subscription_starts_at INTEGER,
            subscription_ends_at INTEGER,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS reset_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL,
            answer TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT 'math',
            is_saved INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS ai_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            model TEXT,
            domain TEXT NOT NULL DEFAULT 'math',
            status INTEGER NOT NULL,
            latency_ms INTEGER NOT NULL,
            error_code TEXT,
            input_type TEXT NOT NULL DEFAULT 'text',
            created_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS platform_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS daily_usage (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            usage_date TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            text_count INTEGER NOT NULL DEFAULT 0,
            image_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, usage_date)
          );
          CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plan_code TEXT NOT NULL DEFAULT 'premium',
            provider TEXT NOT NULL DEFAULT 'admin',
            provider_subscription_id TEXT UNIQUE,
            payment_order_id TEXT,
            status TEXT NOT NULL CHECK(status IN ('pending','active','suspended','canceled','expired')),
            period_start INTEGER,
            period_end INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS payment_orders (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL CHECK(provider IN ('click','payme')),
            plan_code TEXT NOT NULL CHECK(plan_code IN ('premium_monthly','premium_yearly')),
            duration_months INTEGER NOT NULL CHECK(duration_months IN (1,12)),
            amount_uzs INTEGER NOT NULL CHECK(amount_uzs > 0),
            currency TEXT NOT NULL DEFAULT 'UZS' CHECK(currency='UZS'),
            status TEXT NOT NULL CHECK(status IN ('pending','paid','failed','canceled','refunded','expired')),
            created_at INTEGER NOT NULL,
            completed_at INTEGER,
            expires_at INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL REFERENCES payment_orders(id) ON DELETE RESTRICT,
            provider TEXT NOT NULL CHECK(provider IN ('click','payme')),
            provider_transaction_id TEXT NOT NULL,
            provider_payment_id TEXT,
            provider_prepare_id TEXT,
            provider_time INTEGER,
            provider_reason INTEGER,
            status TEXT NOT NULL CHECK(status IN ('prepared','created','paid','failed','canceled','refunded','refund_pending')),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'UZS',
            raw_payload_hash TEXT,
            created_at INTEGER NOT NULL,
            completed_at INTEGER,
            updated_at INTEGER NOT NULL,
            UNIQUE(provider,provider_transaction_id)
          );
          CREATE TABLE IF NOT EXISTS supervisor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL CHECK(module IN ('auth','database','sympy','openrouter','payments','quota')),
            severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            remediation TEXT,
            auto_fixed INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
          CREATE INDEX IF NOT EXISTS idx_problems_user_time ON problems(user_id, created_at DESC);
          CREATE INDEX IF NOT EXISTS idx_requests_time ON ai_requests(created_at DESC);
          CREATE INDEX IF NOT EXISTS idx_supervisor_events_time ON supervisor_events(created_at DESC);
        """)
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "subscription_status" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN subscription_status TEXT NOT NULL DEFAULT 'free'")
        if "subscription_source" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN subscription_source TEXT NOT NULL DEFAULT 'none'")
        if "subscription_starts_at" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN subscription_starts_at INTEGER")
        if "subscription_ends_at" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN subscription_ends_at INTEGER")
        subscription_columns = {row["name"] for row in db.execute("PRAGMA table_info(subscriptions)")}
        if "payment_order_id" not in subscription_columns:
            db.execute("ALTER TABLE subscriptions ADD COLUMN payment_order_id TEXT")
        payment_tx_columns = {row["name"] for row in db.execute("PRAGMA table_info(payment_transactions)")}
        if "provider_payment_id" not in payment_tx_columns:
            db.execute("ALTER TABLE payment_transactions ADD COLUMN provider_payment_id TEXT")
        if "provider_reason" not in payment_tx_columns:
            db.execute("ALTER TABLE payment_transactions ADD COLUMN provider_reason INTEGER")
        db.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_user_time ON payment_orders(user_id,created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_payment_orders_provider_status ON payment_orders(provider,status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_payment_transactions_order ON payment_transactions(order_id,created_at DESC)")
        request_columns = {row["name"] for row in db.execute("PRAGMA table_info(ai_requests)")}
        if "input_type" not in request_columns:
            db.execute("ALTER TABLE ai_requests ADD COLUMN input_type TEXT NOT NULL DEFAULT 'text'")
        # Carry the previous shipped defaults forward for databases that persisted them.
        db.execute("UPDATE platform_settings SET value='100',updated_at=? WHERE key='freeDailyLimit' AND value='5'", (now(),))
        db.execute("UPDATE platform_settings SET value='1000',updated_at=? WHERE key='freeSavedCapacity' AND value='10'", (now(),))
        # Preserve today's existing request history when migrating from Phase 5's log-based quota.
        migration = db.execute("SELECT 1 FROM platform_settings WHERE key='dailyUsageBackfillV1'").fetchone()
        if not migration:
            db.execute("""INSERT OR IGNORE INTO daily_usage(user_id,usage_date,request_count,text_count,image_count)
              SELECT user_id,date(created_at,'unixepoch'),COUNT(*),SUM(CASE WHEN input_type IN ('text','mixed') THEN 1 ELSE 0 END),
              SUM(CASE WHEN input_type IN ('image','mixed') THEN 1 ELSE 0 END)
              FROM ai_requests WHERE user_id IS NOT NULL GROUP BY user_id,date(created_at,'unixepoch')""")
            db.execute("INSERT OR IGNORE INTO platform_settings(key,value,updated_at) VALUES('dailyUsageBackfillV1','true',?)", (now(),))
            # Existing manually assigned Premium users retain access; this is not a payment record.
            db.execute("UPDATE users SET subscription_status='active',subscription_source='admin' WHERE plan='premium' AND subscription_status='free'")
            db.execute("INSERT INTO subscriptions(user_id,plan_code,provider,status,created_at,updated_at) SELECT id,'premium','admin','active',created_at,updated_at FROM users WHERE plan='premium' AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=users.id AND s.provider='admin' AND s.status='active')")
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        db.commit()

    # Admin identity is anchored to the single configured owner account.
    db.execute("UPDATE users SET role='user',updated_at=? WHERE role='admin' AND email<>? COLLATE NOCASE", (now(), OWNER_ADMIN_EMAIL))
    db.execute("UPDATE users SET role='admin',status='active',updated_at=? WHERE email=? COLLATE NOCASE", (now(), OWNER_ADMIN_EMAIL))
    db.commit()

    # Runtime maintenance is skipped during the supervisor audit so repairs can be counted and recorded.
    if run_maintenance:
        stamp = now()
        db.execute("UPDATE subscriptions SET status='expired',updated_at=? WHERE provider IN ('click','payme') AND status='active' AND period_end IS NOT NULL AND period_end<=?", (stamp, stamp))
        db.execute("UPDATE users SET plan='free',subscription_status='expired',subscription_source='none',subscription_starts_at=NULL,subscription_ends_at=NULL,updated_at=? WHERE plan='premium' AND subscription_source='payment' AND subscription_ends_at IS NOT NULL AND subscription_ends_at<=? AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=users.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?)", (stamp, stamp, stamp))
        db.execute("UPDATE payment_transactions SET status='canceled',provider_reason=4,completed_at=?,updated_at=? WHERE provider='payme' AND status='created' AND provider_time IS NOT NULL AND provider_time<=?",
                   (stamp, stamp, (stamp - 43_200) * 1000))
        db.execute("UPDATE payment_orders SET status='expired' WHERE status='pending' AND expires_at<=? AND NOT EXISTS (SELECT 1 FROM payment_transactions t WHERE t.order_id=payment_orders.id AND t.status IN ('prepared','created'))", (stamp,))
        db.commit()
    return db


def now() -> int:
    return int(time.time())


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _payment_order(db: sqlite3.Connection, order_id: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM payment_orders WHERE id=?", (order_id,)).fetchone()


def _activate_payment(db: sqlite3.Connection, order: sqlite3.Row, stamp: int) -> tuple[int, int]:
    """Activate only from a verified provider settlement while the caller owns a DB transaction."""
    user = db.execute("SELECT plan,subscription_status,subscription_source,subscription_ends_at FROM users WHERE id=?", (order["user_id"],)).fetchone()
    start = max(stamp, int(user["subscription_ends_at"] or stamp))
    from calendar import monthrange
    base = datetime.fromtimestamp(start, timezone.utc)
    month_index = base.month - 1 + int(order["duration_months"])
    year, month = base.year + month_index // 12, month_index % 12 + 1
    end = int(base.replace(year=year, month=month, day=min(base.day, monthrange(year, month)[1])).timestamp())
    # Admin grants remain admin-managed. Paid term is still recorded independently.
    if not (user["plan"] == "premium" and user["subscription_source"] == "admin" and user["subscription_status"] == "active"):
        db.execute("UPDATE users SET plan='premium',subscription_status='active',subscription_source='payment',subscription_starts_at=?,subscription_ends_at=?,updated_at=? WHERE id=?",
                   (start, end, stamp, order["user_id"]))
    db.execute("INSERT INTO subscriptions(user_id,plan_code,provider,status,period_start,period_end,created_at,updated_at,payment_order_id) VALUES(?,?,?,'active',?,?,?,?,?)",
               (order["user_id"], order["plan_code"], order["provider"], start, end, stamp, stamp, order["id"]))
    db.execute("UPDATE payment_orders SET status='paid',completed_at=? WHERE id=?", (stamp, order["id"]))
    return start, end


def _revoke_payment(db: sqlite3.Connection, order: sqlite3.Row, stamp: int, final_status: str) -> None:
    db.execute("UPDATE payment_orders SET status=?,completed_at=COALESCE(completed_at,?) WHERE id=?", (final_status, stamp, order["id"]))
    db.execute("UPDATE subscriptions SET status='canceled',updated_at=? WHERE payment_order_id=? AND provider IN ('click','payme')", (stamp, order["id"]))
    user = db.execute("SELECT plan,subscription_source,subscription_ends_at FROM users WHERE id=?", (order["user_id"],)).fetchone()
    if user["subscription_source"] == "payment":
        current = db.execute("SELECT MAX(period_end) FROM subscriptions WHERE user_id=? AND status='active' AND provider IN ('click','payme') AND period_end>?", (order["user_id"], stamp)).fetchone()[0]
        if current:
            db.execute("UPDATE users SET subscription_ends_at=?,updated_at=? WHERE id=?", (current, stamp, order["user_id"]))
        else:
            db.execute("UPDATE users SET plan='free',subscription_status='canceled',subscription_source='none',subscription_starts_at=NULL,subscription_ends_at=NULL,updated_at=? WHERE id=?", (stamp, order["user_id"]))


def _order_json(order: sqlite3.Row, tx: sqlite3.Row | None = None) -> dict[str, Any]:
    result = {"id": order["id"], "provider": order["provider"], "planCode": order["plan_code"], "durationMonths": order["duration_months"],
              "amount": order["amount_uzs"], "currency": order["currency"], "status": order["status"], "createdAt": order["created_at"],
              "completedAt": order["completed_at"], "expiresAt": order["expires_at"]}
    if tx:
        result.update({"providerTransactionId": tx["provider_transaction_id"], "providerPaymentId": tx["provider_payment_id"], "transactionStatus": tx["status"], "transactionCreatedAt": tx["created_at"]})
    return result


def user_json(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"],
            "plan": row["plan"], "subscriptionStatus": row["subscription_status"], "subscriptionSource": row["subscription_source"],
            "subscriptionStartsAt": row["subscription_starts_at"], "subscriptionEndsAt": row["subscription_ends_at"],
            "status": row["status"], "createdAt": row["created_at"]}


def op(data: dict[str, Any]) -> Any:
    action = data.get("op")
    db = connect(run_maintenance=action not in ("supervisor_audit", "health_check"))
    try:
        stamp = now()
        if action == "health_check":
            result = db.execute("PRAGMA quick_check(1)").fetchone()[0]
            if result != "ok": raise RuntimeError("SQLite integrity check failed.")
            return True
        if action == "supervisor_log":
            module = data.get("module")
            severity = data.get("severity")
            if module not in ("auth", "database", "sympy", "openrouter", "payments", "quota") or severity not in ("info", "warning", "critical"):
                raise ValueError("Supervisor hodisasi noto‘g‘ri.")
            code = str(data.get("code", "unknown"))[:80]
            message = str(data.get("message", ""))[:500]
            remediation = data.get("remediation")
            if remediation is not None: remediation = str(remediation)[:500]
            db.execute("INSERT INTO supervisor_events(module,severity,code,message,remediation,auto_fixed,created_at) VALUES(?,?,?,?,?,?,?)",
                       (module, severity, code, message, remediation, int(bool(data.get("autoFixed"))), stamp))
            db.execute("DELETE FROM supervisor_events WHERE created_at<? OR id NOT IN (SELECT id FROM supervisor_events ORDER BY created_at DESC,id DESC LIMIT 500)", (stamp - 30 * 86400,))
            db.commit(); return True
        if action == "supervisor_audit":
            quick = db.execute("PRAGMA quick_check(1)").fetchone()[0]
            fk_issues = db.execute("PRAGMA foreign_key_check").fetchall()
            database_ok = quick == "ok" and not fk_issues
            auto_fix = data.get("runAutoFix", True) is not False
            remediations = {"expiredSessionsPurged": 0, "expiredResetTokensPurged": 0, "staleOrdersExpired": 0,
                            "subscriptionsReconciled": 0, "corruptSettingsFixed": 0}
            stale_tx = 0
            events_to_add: list[tuple[str, str, str, str, str | None, int]] = []
            if auto_fix:
                db.execute("BEGIN IMMEDIATE")
                remediations["expiredSessionsPurged"] = db.execute("DELETE FROM sessions WHERE expires_at<=?", (stamp,)).rowcount
                remediations["expiredResetTokensPurged"] = db.execute("DELETE FROM reset_tokens WHERE expires_at<=?", (stamp,)).rowcount
                stale_tx = db.execute("UPDATE payment_transactions SET status='canceled',provider_reason=4,completed_at=?,updated_at=? WHERE provider='payme' AND status='created' AND provider_time IS NOT NULL AND provider_time<=?",
                                      (stamp, stamp, (stamp - 43_200) * 1000)).rowcount
                remediations["staleOrdersExpired"] = db.execute("UPDATE payment_orders SET status='expired' WHERE status='pending' AND expires_at<=? AND NOT EXISTS (SELECT 1 FROM payment_transactions t WHERE t.order_id=payment_orders.id AND t.status IN ('prepared','created'))", (stamp,)).rowcount
                expired_subs = db.execute("UPDATE subscriptions SET status='expired',updated_at=? WHERE provider IN ('click','payme') AND status='active' AND period_end IS NOT NULL AND period_end<=?", (stamp, stamp)).rowcount
                expired_users = db.execute("UPDATE users SET plan='free',subscription_status='expired',subscription_source='none',subscription_starts_at=NULL,subscription_ends_at=NULL,updated_at=? WHERE plan='premium' AND subscription_source='payment' AND subscription_ends_at IS NOT NULL AND subscription_ends_at<=? AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=users.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?)", (stamp, stamp, stamp)).rowcount
                restored_users = db.execute("UPDATE users SET plan='premium',subscription_status='active',subscription_source='payment',subscription_ends_at=(SELECT MAX(s.period_end) FROM subscriptions s WHERE s.user_id=users.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?),updated_at=? WHERE (plan='free' OR (subscription_source='payment' AND subscription_ends_at<=?)) AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=users.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?)", (stamp, stamp, stamp, stamp)).rowcount
                remediations["subscriptionsReconciled"] = expired_subs + expired_users + restored_users
                safe_defaults = {"freeDailyLimit": 100, "premiumDailyLimit": 100, "freeSavedCapacity": 1000, "premiumSavedCapacity": 1000}
                for key, default in safe_defaults.items():
                    row = db.execute("SELECT value FROM platform_settings WHERE key=?", (key,)).fetchone()
                    if row is None: continue
                    try: value = json.loads(row["value"])
                    except (ValueError, TypeError): value = None
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
                        db.execute("UPDATE platform_settings SET value=?,updated_at=? WHERE key=?", (json.dumps(default), stamp, key))
                        remediations["corruptSettingsFixed"] += 1
                labels = {"expiredSessionsPurged": ("auth", "sessions_purged", "Muddati tugagan sessiyalar tozalandi."),
                          "expiredResetTokensPurged": ("auth", "reset_tokens_purged", "Muddati tugagan parol tiklash tokenlari tozalandi."),
                          "staleOrdersExpired": ("payments", "stale_orders_expired", "Eskirgan to‘lov buyurtmalari yakunlandi."),
                          "subscriptionsReconciled": ("quota", "subscriptions_reconciled", "Obuna holatlari ma’lumotlar bazasi bilan moslashtirildi."),
                          "corruptSettingsFixed": ("quota", "settings_repaired", "Noto‘g‘ri limit sozlamalari xavfsiz qiymatlarga tiklandi.")}
                for key, count in remediations.items():
                    if count:
                        module, code, message = labels[key]
                        events_to_add.append((module, "warning", code, f"{message} Soni: {count}.", "Xavfsiz avtomatik tuzatish bajarildi.", 1))
                if stale_tx:
                    events_to_add.append(("payments", "warning", "payme_stale_transactions", f"12 soatdan eski Payme tranzaksiyalari bekor qilindi. Soni: {stale_tx}.", "Tranzaksiyalar bekor holatiga o‘tkazildi.", 1))

            since = stamp - 3600
            telemetry_row = db.execute("SELECT COUNT(*) requests,COALESCE(SUM(status>=400),0) errors,COALESCE(SUM(status>=500 OR error_code LIKE '%TIMEOUT%' OR error_code LIKE '%timeout%'),0) upstream_failures,COALESCE(AVG(latency_ms),0) avg_latency FROM ai_requests WHERE created_at>=?", (since,)).fetchone()
            telemetry = {"requests": int(telemetry_row["requests"]), "errors": int(telemetry_row["errors"]),
                         "errorRate": (telemetry_row["errors"] / telemetry_row["requests"]) if telemetry_row["requests"] else 0,
                         "avgLatencyMs": round(float(telemetry_row["avg_latency"])), "timeoutUpstreamFailures": int(telemetry_row["upstream_failures"]),
                         "upstreamFailureRate": (telemetry_row["upstream_failures"] / telemetry_row["requests"]) if telemetry_row["requests"] else 0}
            if telemetry["requests"] >= 5 and telemetry["errorRate"] >= 0.30:
                events_to_add.append(("openrouter", "critical", "ai_error_rate_high", f"AI xatolik darajasi so‘nggi soatda {telemetry['errorRate']:.0%} ({telemetry['errors']}/{telemetry['requests']}).", "OpenRouter va server jurnallarini tekshirish tavsiya etiladi.", 0))
            stuck_refunds = db.execute("SELECT COUNT(*) FROM payment_transactions WHERE status='refund_pending'").fetchone()[0]
            failed_callbacks = db.execute("SELECT COUNT(*) FROM payment_transactions WHERE status='failed'").fetchone()[0]
            if stuck_refunds:
                events_to_add.append(("payments", "critical", "refunds_stuck", f"Qaytarish kutilayotgan tranzaksiyalar: {stuck_refunds}.", "Provayder holatini tekshirib, zarur bo‘lsa merchant bilan bog‘laning.", 0))
            if failed_callbacks:
                events_to_add.append(("payments", "warning", "failed_payment_callbacks", f"Muvaffaqiyatsiz to‘lov tranzaksiyalari: {failed_callbacks}.", "Merchant callback jurnallarini tekshiring.", 0))
            if not database_ok:
                events_to_add.append(("database", "critical", "database_integrity_failed", f"SQLite yaxlitlik tekshiruvi natijasi: {quick}; foreign key muammolari: {len(fk_issues)}.", "Zaxira nusxani tekshirib, bazani tiklashni ko‘rib chiqing.", 0))
            if events_to_add:
                db.executemany("INSERT INTO supervisor_events(module,severity,code,message,remediation,auto_fixed,created_at) VALUES(?,?,?,?,?,?,?)",
                               [(module, severity, code, message, remediation, auto_fixed, stamp) for module, severity, code, message, remediation, auto_fixed in events_to_add])
            db.execute("DELETE FROM supervisor_events WHERE created_at<? OR id NOT IN (SELECT id FROM supervisor_events ORDER BY created_at DESC,id DESC LIMIT 500)", (stamp - 30 * 86400,))
            db.commit()
            settings_ok = True
            for key, maximum in (("freeDailyLimit", 10000), ("premiumDailyLimit", 10000), ("freeSavedCapacity", 10000), ("premiumSavedCapacity", 10000)):
                row = db.execute("SELECT value FROM platform_settings WHERE key=?", (key,)).fetchone()
                if row:
                    try: value = json.loads(row["value"])
                    except (ValueError, TypeError): value = None
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum: settings_ok = False
            expired_sessions_remaining = db.execute("SELECT COUNT(*) FROM sessions WHERE expires_at<=?", (stamp,)).fetchone()[0]
            expired_tokens_remaining = db.execute("SELECT COUNT(*) FROM reset_tokens WHERE expires_at<=?", (stamp,)).fetchone()[0]
            stale_orders_remaining = db.execute("SELECT COUNT(*) FROM payment_orders o WHERE o.status='pending' AND o.expires_at<=? AND NOT EXISTS (SELECT 1 FROM payment_transactions t WHERE t.order_id=o.id AND t.status IN ('prepared','created'))", (stamp,)).fetchone()[0]
            stale_payme_remaining = db.execute("SELECT COUNT(*) FROM payment_transactions WHERE provider='payme' AND status='created' AND provider_time IS NOT NULL AND provider_time<=?", ((stamp - 43_200) * 1000,)).fetchone()[0]
            subscription_mismatches = db.execute("SELECT COUNT(*) FROM users u WHERE (u.plan='free' AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?)) OR (u.plan='premium' AND u.subscription_source='payment' AND u.subscription_ends_at<=? AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id=u.id AND s.provider IN ('click','payme') AND s.status='active' AND s.period_end>?))", (stamp, stamp, stamp)).fetchone()[0]
            modules = {
                "database": {"status": "healthy" if database_ok else "critical", "quickCheck": quick, "foreignKeyIssues": len(fk_issues)},
                "auth": {"status": "warning" if expired_sessions_remaining or expired_tokens_remaining else "healthy", "expiredSessions": int(expired_sessions_remaining), "expiredResetTokens": int(expired_tokens_remaining)},
                "quota": {"status": "warning" if not settings_ok or subscription_mismatches else "healthy", "settingsValid": settings_ok, "subscriptionMismatches": int(subscription_mismatches)},
                "payments": {"status": "critical" if stuck_refunds else "warning" if failed_callbacks or stale_orders_remaining or stale_payme_remaining else "healthy", "stuckRefunds": int(stuck_refunds), "failedTransactions": int(failed_callbacks), "staleOrders": int(stale_orders_remaining), "stalePaymeTransactions": int(stale_payme_remaining)},
                "ai_telemetry": {"status": "critical" if telemetry["requests"] >= 5 and telemetry["errorRate"] >= 0.30 else "healthy"},
            }
            events = [dict(id=r["id"], module=r["module"], severity=r["severity"], code=r["code"], message=r["message"], remediation=r["remediation"], autoFixed=bool(r["auto_fixed"]), createdAt=r["created_at"]) for r in db.execute("SELECT * FROM supervisor_events ORDER BY created_at DESC,id DESC LIMIT 50").fetchall()]
            return {"healthy": database_ok and all(item["status"] == "healthy" for item in modules.values()), "checkedAt": stamp, "modules": modules,
                    "remediations": remediations, "telemetryLastHour": telemetry, "events": events}
        if action == "register":
            email, name, password = data["email"].strip().lower(), data["name"].strip(), data["password"]
            if not re.fullmatch(r"[^\s@]{1,64}@[^\s@.]+(?:\.[^\s@.]+)+", email):
                raise ValueError("Email manzili noto‘g‘ri.")
            if len(name) < 2 or len(name) > 80:
                raise ValueError("Ism 2–80 belgi oralig‘ida bo‘lishi kerak.")
            if len(password) < 10 or len(password) > 256:
                raise ValueError("Parol kamida 10 belgidan iborat bo‘lishi kerak.")
            if len(email) > 254:
                raise ValueError("Email manzili 254 belgidan uzun bo‘lmasligi kerak.")
            salt = secrets.token_bytes(16)
            password_hash = __import__("hashlib").scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
            try:
                cur = db.execute("INSERT INTO users(email,name,password_hash,password_salt,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                                 (email, name, password_hash, salt.hex(), stamp, stamp))
                if email.lower() == OWNER_ADMIN_EMAIL:
                    db.execute("UPDATE users SET role='admin',status='active',updated_at=? WHERE id=?", (stamp, cur.lastrowid))
                db.commit()
            except sqlite3.IntegrityError:
                raise ValueError("Bu email bilan hisob mavjud.")
            return user_json(db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
        if action == "login":
            row = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (data["email"].strip(),)).fetchone()
            import hashlib
            candidate = hashlib.scrypt(data["password"].encode(), salt=bytes.fromhex(row["password_salt"]) if row else b"mathai-invalid-salt", n=2**14, r=8, p=1).hex()
            import hmac
            valid = bool(row and hmac.compare_digest(candidate, row["password_hash"]) and row["status"] == "active")
            if not valid:
                raise PermissionError("Email yoki parol noto‘g‘ri.")
            db.execute("DELETE FROM sessions WHERE user_id=? AND expires_at<=?", (row["id"], stamp))
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                       (data["tokenHash"], row["id"], data["expiresAt"], stamp))
            db.commit()
            return user_json(row)
        if action == "register_session":
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                       (data["tokenHash"], data["userId"], data["expiresAt"], stamp))
            db.commit()
            return True
        if action == "session":
            row = db.execute("SELECT u.*,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (data["tokenHash"],)).fetchone()
            if not row or row["expires_at"] <= stamp or row["status"] != "active":
                if row:
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (data["tokenHash"],)); db.commit()
                return None
            return user_json(row)
        if action == "logout":
            db.execute("DELETE FROM sessions WHERE token_hash=?", (data["tokenHash"],)); db.commit(); return True
        if action == "profile":
            if not 2 <= len(data["name"].strip()) <= 80:
                raise ValueError("Ism 2–80 belgi oralig‘ida bo‘lishi kerak.")
            db.execute("UPDATE users SET name=?,updated_at=? WHERE id=?", (data["name"].strip(), stamp, data["userId"]))
            db.commit(); return user_json(db.execute("SELECT * FROM users WHERE id=?", (data["userId"],)).fetchone())
        if action == "change_password":
            row = db.execute("SELECT * FROM users WHERE id=?", (data["userId"],)).fetchone()
            import hashlib, hmac
            old = hashlib.scrypt(data["currentPassword"].encode(), salt=bytes.fromhex(row["password_salt"]), n=2**14, r=8, p=1).hex()
            if not hmac.compare_digest(old, row["password_hash"]): raise PermissionError("Joriy parol noto‘g‘ri.")
            if len(data["newPassword"]) < 10 or len(data["newPassword"]) > 256: raise ValueError("Yangi parol kamida 10 belgidan iborat bo‘lishi kerak.")
            salt = secrets.token_bytes(16); hashed = hashlib.scrypt(data["newPassword"].encode(), salt=salt, n=2**14, r=8, p=1).hex()
            db.execute("UPDATE users SET password_hash=?,password_salt=?,updated_at=? WHERE id=?", (hashed, salt.hex(), stamp, data["userId"]))
            db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (data["userId"], data.get("currentTokenHash", ""))); db.commit(); return True
        if action == "create_reset":
            row = db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE AND status='active'", (data["email"].strip(),)).fetchone()
            if row:
                db.execute("DELETE FROM reset_tokens WHERE user_id=?", (row["id"],))
                db.execute("INSERT INTO reset_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                           (data["tokenHash"], row["id"], data["expiresAt"], stamp))
                db.commit(); return True
            return False
        if action == "reset_password":
            row = db.execute("SELECT u.id FROM reset_tokens r JOIN users u ON u.id=r.user_id WHERE r.token_hash=? AND r.expires_at>? AND u.status='active'", (data["tokenHash"], stamp)).fetchone()
            if not row: raise PermissionError("Havola yaroqsiz yoki muddati tugagan.")
            if len(data["password"]) < 10 or len(data["password"]) > 256: raise ValueError("Parol kamida 10 belgidan iborat bo‘lishi kerak.")
            import hashlib
            salt = secrets.token_bytes(16); hashed = hashlib.scrypt(data["password"].encode(), salt=salt, n=2**14, r=8, p=1).hex()
            db.execute("UPDATE users SET password_hash=?,password_salt=?,updated_at=? WHERE id=?", (hashed, salt.hex(), stamp, row["id"]))
            db.execute("DELETE FROM reset_tokens WHERE user_id=?", (row["id"],)); db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],)); db.commit(); return True
        if action == "history":
            rows = db.execute("SELECT id,prompt,answer,domain,is_saved,created_at FROM problems WHERE user_id=? ORDER BY created_at DESC LIMIT 2000", (data["userId"],)).fetchall()
            total = db.execute("SELECT COUNT(*) n FROM problems WHERE user_id=?", (data["userId"],)).fetchone()["n"]
            return {"items": [dict(id=r["id"], prompt=r["prompt"], answer=r["answer"], domain=r["domain"], saved=bool(r["is_saved"]), createdAt=r["created_at"]) for r in rows],
                    "total": total, "saved": sum(r["is_saved"] for r in rows), "byDomain": dict(db.execute("SELECT domain,COUNT(*) n FROM problems WHERE user_id=? GROUP BY domain", (data["userId"],)).fetchall())}
        if action == "usage":
            settings = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key,value FROM platform_settings").fetchall()}
            user = db.execute("SELECT plan,subscription_status,subscription_source,subscription_starts_at,subscription_ends_at FROM users WHERE id=?", (data["userId"],)).fetchone()
            if not user: raise PermissionError("Hisob topilmadi.")
            effective_plan = "free"
            limit = int(settings.get("freeDailyLimit", 100))
            day = utc_date()
            usage = db.execute("SELECT request_count,text_count,image_count FROM daily_usage WHERE user_id=? AND usage_date=?", (data["userId"], day)).fetchone()
            used, text_count, image_count = (usage[0], usage[1], usage[2]) if usage else (0, 0, 0)
            resets_at = int((datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
            features_key = "freePlanFeatures"
            saved_capacity = int(settings.get("freeSavedCapacity", 1000))
            saved_count = db.execute("SELECT COUNT(*) FROM problems WHERE user_id=? AND is_saved=1", (data["userId"],)).fetchone()[0]
            defaults = {"freePlanFeatures": ["Kuniga 100 ta masala", "Matematika va geometriya", "Bosqichma-bosqich yechimlar", "SymPy tekshiruvi", "Rasm orqali masala yechish", "Yechimlarni saqlash"],
                        "premiumPlanFeatures": ["Kuniga 100 ta masala", "Kengaytirilgan nazariya", "Barcha matematika va geometriya", "Tezroq AI yo‘naltirish"]}
            plan_features = list(settings.get(features_key, defaults[features_key]))
            plan_features = [feature for feature in plan_features if not re.match(r"^Kuniga \d+ ta masala$", str(feature))]
            plan_features.insert(0, f"Kuniga {limit} ta masala")
            return {"used": used, "textRequests": text_count, "imageRequests": image_count, "limit": limit, "remaining": max(0, limit-used),
                    "plan": effective_plan, "assignedPlan": user["plan"], "subscriptionStatus": user["subscription_status"],
                    "subscriptionSource": user["subscription_source"], "subscriptionStartsAt": user["subscription_starts_at"],
                    "subscriptionEndsAt": user["subscription_ends_at"], "features": plan_features,
                    "premiumExtendedExplanations": True,
                    "premiumPriorityRouting": True,
                    "savedCapacity": saved_capacity, "savedCount": saved_count, "usageDate": day, "resetsAt": resets_at}
        if action == "check_global_limit":
            day = utc_date()
            day_start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
            resets_at = int((datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
            global_limit = max(1, int(os.environ.get("MATHAI_GLOBAL_DAILY_LIMIT", "2000")))
            global_used = db.execute("SELECT COUNT(*) FROM ai_requests WHERE created_at >= ?", (day_start,)).fetchone()[0]
            return {"allowed": global_used < global_limit, "used": global_used, "limit": global_limit, "resetsAt": resets_at}
        if action == "reserve_usage":
            db.execute("BEGIN IMMEDIATE")
            settings = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key,value FROM platform_settings").fetchall()}
            user = db.execute("SELECT plan,subscription_status,status FROM users WHERE id=?", (data["userId"],)).fetchone()
            if not user or user["status"] != "active":
                db.rollback(); raise PermissionError("Hisob faol emas.")
            effective_plan = "free"
            limit = int(settings.get("freeDailyLimit", 100))
            day = utc_date()
            day_start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
            global_limit = max(1, int(os.environ.get("MATHAI_GLOBAL_DAILY_LIMIT", "2000")))
            global_used = db.execute("SELECT COUNT(*) FROM ai_requests WHERE created_at >= ?", (day_start,)).fetchone()[0]
            row = db.execute("SELECT request_count FROM daily_usage WHERE user_id=? AND usage_date=?", (data["userId"], day)).fetchone()
            used = row[0] if row else 0
            resets_at = int((datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
            if global_used >= global_limit:
                db.commit()
                return {"allowed": False, "reason": "global_limit", "used": used, "limit": limit, "remaining": max(0, limit-used), "plan": effective_plan, "usageDate": day, "resetsAt": resets_at,
                        "premiumExtendedExplanations": True,
                        "premiumPriorityRouting": True}
            if used >= limit:
                db.commit()
                return {"allowed": False, "used": used, "limit": limit, "remaining": 0, "plan": effective_plan, "usageDate": day, "resetsAt": resets_at,
                        "premiumExtendedExplanations": True,
                        "premiumPriorityRouting": True}
            db.execute("""INSERT INTO daily_usage(user_id,usage_date,request_count,text_count,image_count) VALUES(?,?,?,?,?)
              ON CONFLICT(user_id,usage_date) DO UPDATE SET request_count=request_count+1,text_count=text_count+excluded.text_count,image_count=image_count+excluded.image_count""",
              (data["userId"], day, 1, int(bool(data.get("hasText"))), int(bool(data.get("hasImage")))))
            db.commit(); used += 1
            return {"allowed": True, "used": used, "limit": limit, "remaining": max(0, limit-used), "plan": effective_plan, "usageDate": day, "resetsAt": resets_at,
                    "premiumExtendedExplanations": True,
                    "premiumPriorityRouting": True}
        if action == "save_problem":
            cur = db.execute("INSERT INTO problems(user_id,prompt,answer,domain,created_at) VALUES(?,?,?,?,?)", (data["userId"], data["prompt"][:12000], data["answer"][:24000], data.get("domain", "math"), stamp)); db.commit(); return cur.lastrowid
        if action == "toggle_saved":
            item = db.execute("SELECT is_saved FROM problems WHERE id=? AND user_id=?", (data["problemId"], data["userId"])).fetchone()
            if not item: return {"ok": False, "reason": "missing"}
            target = 0 if item["is_saved"] else 1
            if target:
                settings = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key,value FROM platform_settings").fetchall()}
                user = db.execute("SELECT plan,subscription_status FROM users WHERE id=?", (data["userId"],)).fetchone()
                capacity = int(settings.get("freeSavedCapacity", 1000))
                current = db.execute("SELECT COUNT(*) FROM problems WHERE user_id=? AND is_saved=1", (data["userId"],)).fetchone()[0]
                if current >= capacity: return {"ok": False, "reason": "capacity", "capacity": capacity}
            db.execute("UPDATE problems SET is_saved=? WHERE id=? AND user_id=?", (target, data["problemId"], data["userId"])); db.commit()
            return {"ok": True, "saved": bool(target)}
        if action == "delete_problem":
            cur = db.execute("DELETE FROM problems WHERE id=? AND user_id=?", (data["problemId"], data["userId"])); db.commit(); return cur.rowcount == 1
        if action == "payment_create_order":
            db.execute("BEGIN IMMEDIATE")
            idem = db.execute("SELECT * FROM payment_orders WHERE idempotency_key=?", (data["idempotencyKey"],)).fetchone()
            if idem:
                if (idem["user_id"], idem["provider"], idem["plan_code"], idem["amount_uzs"]) != (data["userId"], data["provider"], data["planCode"], data["amountUZS"]):
                    db.rollback(); raise ValueError("Idempotency key boshqa buyurtma uchun ishlatilgan.")
                db.commit(); return _order_json(idem)
            if data["provider"] not in ("click", "payme") or data["planCode"] not in ("premium_monthly", "premium_yearly"):
                db.rollback(); raise ValueError("To‘lov rejasi yoki provayder noto‘g‘ri.")
            months = 1 if data["planCode"] == "premium_monthly" else 12
            db.execute("INSERT INTO payment_orders(id,idempotency_key,user_id,provider,plan_code,duration_months,amount_uzs,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'pending',?,?)",
                       (data["id"], data["idempotencyKey"], data["userId"], data["provider"], data["planCode"], months, data["amountUZS"], stamp, stamp + 43_200))
            db.commit(); return _order_json(_payment_order(db, data["id"]))
        if action == "payment_user_orders":
            rows = db.execute("SELECT * FROM payment_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (data["userId"],)).fetchall()
            return [_order_json(r, db.execute("SELECT * FROM payment_transactions WHERE order_id=? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()) for r in rows]
        if action == "payment_order_status":
            order = db.execute("SELECT * FROM payment_orders WHERE id=? AND user_id=?", (data["id"], data["userId"])).fetchone()
            if not order: return None
            return _order_json(order, db.execute("SELECT * FROM payment_transactions WHERE order_id=? ORDER BY id DESC LIMIT 1", (order["id"],)).fetchone())
        if action == "payment_admin_order":
            order = _payment_order(db, data["id"])
            if not order: return None
            return {"provider": order["provider"], "status": order["status"], "providerPaymentId": (db.execute("SELECT provider_payment_id FROM payment_transactions WHERE order_id=? ORDER BY id DESC LIMIT 1", (order["id"],)).fetchone() or [None])[0]}
        if action == "payment_check_order":
            order = _payment_order(db, data["id"])
            if not order or order["provider"] != data["provider"]: return None
            return {"id": order["id"], "amount": order["amount_uzs"], "amountMinor": order["amount_uzs"] * 100,
                    "status": order["status"], "expiresAt": order["expires_at"], "createdAt": order["created_at"]}
        if action == "payment_admin_list":
            provider, status = data.get("provider"), data.get("status")
            where, args = [], []
            if provider in ("click", "payme"): where.append("o.provider=?"); args.append(provider)
            if status in ("pending", "paid", "failed", "canceled", "refunded", "expired"): where.append("o.status=?"); args.append(status)
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            rows = db.execute("SELECT o.*,u.email,u.name FROM payment_orders o JOIN users u ON u.id=o.user_id" + clause + " ORDER BY o.created_at DESC LIMIT 500", args).fetchall()
            orders = []
            for r in rows:
                item = _order_json(r, db.execute("SELECT * FROM payment_transactions WHERE order_id=? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone())
                item.update({"userId": r["user_id"], "email": r["email"], "name": r["name"]}); orders.append(item)
            totals = db.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN status='paid' THEN amount_uzs ELSE 0 END),0) revenue,COUNT(CASE WHEN status='paid' THEN 1 END) paid,COUNT(CASE WHEN status IN ('failed','canceled') THEN 1 END) failed FROM payment_orders" + clause, args).fetchone()
            return {"orders": orders, "stats": dict(total=totals["total"], revenueUZS=totals["revenue"], paid=totals["paid"], failed=totals["failed"])}
        if action == "payment_click_prepare":
            db.execute("BEGIN IMMEDIATE")
            order = _payment_order(db, data["orderId"])
            if not order or order["provider"] != "click":
                db.rollback(); return {"ok": False, "reason": "order"}
            if order["amount_uzs"] * 100 != data["amountMinor"]:
                db.rollback(); return {"ok": False, "reason": "amount"}
            if order["status"] != "pending":
                db.rollback(); return {"ok": False, "reason": "paid" if order["status"] == "paid" else "state"}
            existing = db.execute("SELECT * FROM payment_transactions WHERE provider='click' AND provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if existing:
                if existing["order_id"] != order["id"] or existing["amount_minor"] != data["amountMinor"]:
                    db.rollback(); return {"ok": False, "reason": "transaction"}
                db.commit(); return {"ok": True, "prepareId": existing["provider_prepare_id"], "duplicate": True}
            cur = db.execute("INSERT INTO payment_transactions(order_id,provider,provider_transaction_id,provider_payment_id,provider_prepare_id,status,amount_minor,currency,raw_payload_hash,created_at,updated_at) VALUES(?,'click',?,?,NULL,'prepared',?,'UZS',?,?,?)",
                             (order["id"], data["transactionId"], data.get("paymentId"), data["amountMinor"], data.get("payloadHash"), stamp, stamp))
            prepare_id = str(cur.lastrowid)
            db.execute("UPDATE payment_transactions SET provider_prepare_id=? WHERE id=?", (prepare_id, cur.lastrowid)); db.commit()
            return {"ok": True, "prepareId": prepare_id, "duplicate": False}
        if action == "payment_click_complete":
            db.execute("BEGIN IMMEDIATE")
            tx = db.execute("SELECT t.*,o.*,o.id AS payment_order_id FROM payment_transactions t JOIN payment_orders o ON o.id=t.order_id WHERE t.provider='click' AND t.provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if not tx or tx["provider_prepare_id"] != str(data["prepareId"]) or tx["payment_order_id"] != data["orderId"]:
                db.rollback(); return {"ok": False, "reason": "transaction"}
            order = _payment_order(db, tx["order_id"])
            if order["amount_uzs"] * 100 != data["amountMinor"]:
                db.rollback(); return {"ok": False, "reason": "amount"}
            if order["status"] == "paid":
                db.commit(); return {"ok": True, "duplicate": True, "order": _order_json(order)}
            if order["status"] == "canceled" or tx["status"] == "canceled":
                if data["providerError"] != 0:
                    db.commit(); return {"ok": True, "canceled": True, "duplicate": True}
                db.rollback(); return {"ok": False, "reason": "canceled"}
            if data["providerError"] != 0:
                db.execute("UPDATE payment_transactions SET status='canceled',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
                db.execute("UPDATE payment_orders SET status='canceled',completed_at=? WHERE id=?", (stamp, order["id"]))
                db.commit(); return {"ok": True, "canceled": True, "duplicate": False}
            if order["status"] != "pending" or tx["status"] != "prepared":
                db.rollback(); return {"ok": False, "reason": "state"}
            db.execute("UPDATE payment_transactions SET status='paid',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
            start, end = _activate_payment(db, order, stamp)
            db.commit(); return {"ok": True, "duplicate": False, "subscriptionStartsAt": start, "subscriptionEndsAt": end}
        if action == "payment_payme_create":
            db.execute("BEGIN IMMEDIATE")
            order = _payment_order(db, data["orderId"])
            if not order or order["provider"] != "payme": db.rollback(); return {"ok": False, "reason": "order"}
            if order["amount_uzs"] * 100 != data["amountMinor"]:
                db.rollback(); return {"ok": False, "reason": "amount_or_state"}
            existing = db.execute("SELECT * FROM payment_transactions WHERE provider='payme' AND provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if existing:
                if existing["order_id"] != order["id"] or existing["amount_minor"] != data["amountMinor"]:
                    db.rollback(); return {"ok": False, "reason": "transaction"}
                db.commit(); return {"ok": True, "duplicate": True, "transaction": existing["id"], "status": existing["status"], "createdAt": existing["created_at"] * 1000}
            if order["status"] != "pending" or order["expires_at"] <= stamp:
                db.rollback(); return {"ok": False, "reason": "amount_or_state"}
            if data["providerTime"] < stamp * 1000 - 43_200_000:
                db.rollback(); return {"ok": False, "reason": "timeout"}
            cur = db.execute("INSERT INTO payment_transactions(order_id,provider,provider_transaction_id,provider_time,status,amount_minor,currency,raw_payload_hash,created_at,updated_at) VALUES(?,'payme',?,?, 'created',?,'UZS',?,?,?)",
                             (order["id"], data["transactionId"], data["providerTime"], data["amountMinor"], data.get("payloadHash"), stamp, stamp))
            db.commit(); return {"ok": True, "duplicate": False, "transaction": cur.lastrowid, "status": "created", "createdAt": stamp * 1000}
        if action == "payment_payme_perform":
            db.execute("BEGIN IMMEDIATE")
            tx = db.execute("SELECT * FROM payment_transactions WHERE provider='payme' AND provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if not tx: db.rollback(); return {"ok": False, "reason": "not_found"}
            order = _payment_order(db, tx["order_id"])
            if order["status"] == "paid" and tx["status"] == "paid":
                db.commit(); return {"ok": True, "duplicate": True, "transaction": tx["id"], "performTime": tx["completed_at"] * 1000}
            if tx["status"] != "created" or order["status"] != "pending": db.rollback(); return {"ok": False, "reason": "state"}
            db.execute("UPDATE payment_transactions SET status='paid',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
            _activate_payment(db, order, stamp)
            db.commit(); return {"ok": True, "duplicate": False, "transaction": tx["id"], "performTime": stamp * 1000}
        if action == "payment_payme_cancel":
            db.execute("BEGIN IMMEDIATE")
            tx = db.execute("SELECT * FROM payment_transactions WHERE provider='payme' AND provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if not tx: db.rollback(); return {"ok": False, "reason": "not_found"}
            order = _payment_order(db, tx["order_id"])
            if tx["status"] in ("canceled", "refunded"):
                db.commit(); return {"ok": True, "duplicate": True, "transaction": tx["id"], "cancelTime": tx["completed_at"] * 1000, "state": -2 if tx["status"] == "refunded" else -1}
            refunded = tx["status"] == "paid"
            final = "refunded" if refunded else "canceled"
            db.execute("UPDATE payment_transactions SET status=?,provider_reason=?,completed_at=?,updated_at=? WHERE id=?", (final, data.get("providerReason"), stamp, stamp, tx["id"]))
            _revoke_payment(db, order, stamp, final)
            db.commit(); return {"ok": True, "duplicate": False, "transaction": tx["id"], "cancelTime": stamp * 1000, "state": -2 if refunded else -1}
        if action == "payment_payme_check":
            tx = db.execute("SELECT t.*,o.status order_status FROM payment_transactions t JOIN payment_orders o ON o.id=t.order_id WHERE t.provider='payme' AND t.provider_transaction_id=?", (data["transactionId"],)).fetchone()
            if not tx: return None
            state = -2 if tx["status"] == "refunded" else -1 if tx["status"] == "canceled" else 2 if tx["status"] == "paid" else 1
            return {"transaction": str(tx["id"]), "createTime": tx["created_at"] * 1000,
                    "performTime": (tx["completed_at"] or 0) * 1000 if tx["status"] in ("paid", "refunded") else 0,
                    "cancelTime": (tx["completed_at"] or 0) * 1000 if tx["status"] in ("canceled", "refunded") else 0,
                    "state": state, "reason": tx["provider_reason"]}
        if action == "payment_payme_statement":
            rows = db.execute("SELECT t.*,o.id order_id,o.amount_uzs,o.status order_status FROM payment_transactions t JOIN payment_orders o ON o.id=t.order_id WHERE t.provider='payme' AND t.provider_time BETWEEN ? AND ? ORDER BY t.provider_time ASC LIMIT 1000", (data["from"], data["to"])).fetchall()
            return [{"id": r["provider_transaction_id"], "time": r["provider_time"], "amount": r["amount_minor"], "account": {"order_id": r["order_id"]},
                     "create_time": r["created_at"] * 1000, "perform_time": (r["completed_at"] or 0) * 1000 if r["status"] == "paid" else 0,
                     "cancel_time": (r["completed_at"] or 0) * 1000 if r["status"] in ("canceled", "refunded") else 0,
                     "transaction": str(r["id"]), "state": 2 if r["status"] == "paid" else -2 if r["status"] == "refunded" else -1 if r["status"] == "canceled" else 1,
                     "reason": r["provider_reason"]} for r in rows]
        if action == "payment_click_refund_prepare":
            db.execute("BEGIN IMMEDIATE")
            order = _payment_order(db, data["orderId"])
            tx = db.execute("SELECT * FROM payment_transactions WHERE order_id=? AND provider='click' ORDER BY id DESC LIMIT 1", (data["orderId"],)).fetchone()
            if not order or order["status"] != "paid" or not tx or tx["status"] != "paid" or not tx["provider_payment_id"]:
                db.rollback(); return {"ok": False}
            db.execute("UPDATE payment_transactions SET status='refund_pending',updated_at=? WHERE id=?", (stamp, tx["id"]))
            db.commit(); return {"ok": True, "paymentId": tx["provider_payment_id"]}
        if action == "payment_click_refund_finish":
            db.execute("BEGIN IMMEDIATE")
            tx = db.execute("SELECT * FROM payment_transactions WHERE order_id=? AND provider='click' AND status='refund_pending' ORDER BY id DESC LIMIT 1", (data["orderId"],)).fetchone()
            order = _payment_order(db, data["orderId"])
            if not tx or not order: db.rollback(); return False
            if data["success"]:
                db.execute("UPDATE payment_transactions SET status='refunded',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
                _revoke_payment(db, order, stamp, "refunded")
            else:
                db.execute("UPDATE payment_transactions SET status='paid',updated_at=? WHERE id=?", (stamp, tx["id"]))
            db.commit(); return bool(data["success"])
        if action == "payment_click_reconcile":
            db.execute("BEGIN IMMEDIATE")
            order = _payment_order(db, data["orderId"])
            tx = db.execute("SELECT * FROM payment_transactions WHERE order_id=? AND provider='click' ORDER BY id DESC LIMIT 1", (data["orderId"],)).fetchone()
            if not order or not tx: db.rollback(); return {"ok": False, "status": "missing"}
            if order["status"] == "paid": db.commit(); return {"ok": True, "status": "paid", "duplicate": True}
            if order["status"] != "pending" or tx["status"] != "prepared": db.rollback(); return {"ok": False, "status": order["status"]}
            provider_status = int(data["providerStatus"])
            if provider_status > 0:
                db.execute("UPDATE payment_transactions SET status='paid',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
                _activate_payment(db, order, stamp); db.commit(); return {"ok": True, "status": "paid", "duplicate": False}
            if provider_status == -99:
                db.execute("UPDATE payment_transactions SET status='canceled',completed_at=?,updated_at=? WHERE id=?", (stamp, stamp, tx["id"]))
                db.execute("UPDATE payment_orders SET status='canceled',completed_at=? WHERE id=?", (stamp, order["id"]))
                db.commit(); return {"ok": True, "status": "canceled", "duplicate": False}
            db.commit(); return {"ok": True, "status": "pending", "duplicate": False}
        if action == "admin_stats":
            scalar = lambda sql: db.execute(sql).fetchone()[0]
            day = utc_date()
            return {"users": scalar("SELECT COUNT(*) FROM users"), "activeUsers": scalar("SELECT COUNT(*) FROM users WHERE status='active'"),
                    "premiumUsers": scalar("SELECT COUNT(*) FROM users WHERE plan='premium' AND subscription_status='active'"),
                    "suspendedPremiumUsers": scalar("SELECT COUNT(*) FROM users WHERE plan='premium' AND subscription_status='suspended'"),
                    "freeUsers": scalar("SELECT COUNT(*) FROM users WHERE plan='free' OR subscription_status<>'active'"), "problems": scalar("SELECT COUNT(*) FROM problems"),
                    "requests": scalar("SELECT COUNT(*) FROM ai_requests"), "errors": scalar("SELECT COUNT(*) FROM ai_requests WHERE status>=400"),
                    "requestsToday": db.execute("SELECT COALESCE(SUM(request_count),0) FROM daily_usage WHERE usage_date=?", (day,)).fetchone()[0],
                    "textRequestsToday": db.execute("SELECT COALESCE(SUM(text_count),0) FROM daily_usage WHERE usage_date=?", (day,)).fetchone()[0],
                    "imageRequestsToday": db.execute("SELECT COALESCE(SUM(image_count),0) FROM daily_usage WHERE usage_date=?", (day,)).fetchone()[0],
                    "recentRequests": [dict(domain=r[0], status=r[1], latencyMs=r[2], model=r[3], inputType=r[4], createdAt=r[5]) for r in db.execute("SELECT domain,status,latency_ms,model,input_type,created_at FROM ai_requests ORDER BY id DESC LIMIT 20").fetchall()]}
        if action == "list_users":
            rows = db.execute("""SELECT u.id,u.email,u.name,u.role,u.plan,u.subscription_status,u.subscription_source,u.status,u.created_at,
              COALESCE(d.request_count,0) used_today FROM users u LEFT JOIN daily_usage d ON d.user_id=u.id AND d.usage_date=? ORDER BY u.created_at DESC LIMIT 200""", (utc_date(),)).fetchall()
            return [dict(id=r[0], email=r[1], name=r[2], role=r[3], plan=r[4], subscriptionStatus=r[5], subscriptionSource=r[6], status=r[7], createdAt=r[8], usedToday=r[9]) for r in rows]
        if action == "admin_user":
            if data.get("status") not in (None, "active", "disabled") or data.get("plan") not in (None, "free", "premium") or data.get("subscriptionStatus") not in (None, "free", "active", "suspended", "expired"):
                raise ValueError("Hisob holati yoki tarif yaroqsiz.")
            if data.get("plan") == "premium" and data.get("subscriptionStatus") not in (None, "active", "suspended", "expired"):
                raise ValueError("Premium rejaga yaroqli obuna holatini belgilang.")
            if data.get("plan") == "free" and data.get("subscriptionStatus") not in (None, "free"):
                raise ValueError("Bepul rejada Premium obuna holati bo‘lishi mumkin emas.")
            target = db.execute("SELECT role,plan,subscription_status FROM users WHERE id=?", (data["targetId"],)).fetchone()
            if not target: raise ValueError("Foydalanuvchi topilmadi.")
            target_email = db.execute("SELECT email FROM users WHERE id=?", (data["targetId"],)).fetchone()["email"]
            if data.get("role") == "admin" and target_email.lower() != OWNER_ADMIN_EMAIL:
                raise ValueError("Faqat platforma egasiga administrator huquqi beriladi.")
            if target_email.lower() == OWNER_ADMIN_EMAIL and (data.get("role") == "user" or data.get("status") == "disabled"):
                raise ValueError("Ega hisobining administrator ruxsatini o‘zgartirib bo‘lmaydi.")
            if data.get("subscriptionStatus") == "free" and data.get("plan") is None and target["plan"] == "premium":
                raise ValueError("Premiumni olib tashlash uchun foydalanuvchini Bepul rejaga o‘tkazing.")
            if data["targetId"] == data["actorId"] and (data.get("status") == "disabled" or data.get("role") == "user"):
                raise ValueError("Administrator o‘zining admin ruxsatini o‘zgartira olmaydi.")
            if target["role"] == "admin" and (data.get("status") == "disabled" or data.get("role") == "user"):
                admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='active'").fetchone()[0]
                if admins <= 1:
                    raise ValueError("Oxirgi faol administratorni o‘zgartirib bo‘lmaydi.")
            fields, values = [], []
            allowed_fields = {"status": "status", "plan": "plan", "role": "role", "subscriptionStatus": "subscription_status"}
            for key, column in allowed_fields.items():
                if key == "subscriptionStatus" and data.get("plan") is not None:
                    continue
                if data.get(key) is not None:
                    if key == "role" and data[key] not in ("user", "admin"): raise ValueError("Role yaroqsiz.")
                    fields.append(f"{column}=?"); values.append(data[key])
            if data.get("plan") == "premium":
                fields.extend(["subscription_status=?", "subscription_source=?", "subscription_starts_at=NULL", "subscription_ends_at=NULL"])
                values.extend([data.get("subscriptionStatus", "active"), "admin"])
            elif data.get("plan") == "free":
                fields.extend(["subscription_status=?", "subscription_source=?", "subscription_starts_at=NULL", "subscription_ends_at=NULL"])
                values.extend(["free", "none"])
            elif data.get("subscriptionStatus") in ("active", "suspended", "expired") and target["plan"] != "premium":
                raise ValueError("Premium holatini faqat Premium rejadagi hisobda o‘zgartirish mumkin.")
            if fields:
                values.extend([stamp, data["targetId"]]); db.execute(f"UPDATE users SET {','.join(fields)},updated_at=? WHERE id=?", values)
                if data.get("status") == "disabled": db.execute("DELETE FROM sessions WHERE user_id=?", (data["targetId"],))
                if data.get("plan") is not None or data.get("subscriptionStatus") is not None:
                    user = db.execute("SELECT plan,subscription_status FROM users WHERE id=?", (data["targetId"],)).fetchone()
                    sub_status = user["subscription_status"] if user["plan"] == "premium" else "canceled"
                    db.execute("INSERT INTO subscriptions(user_id,plan_code,provider,status,created_at,updated_at) VALUES(?,'premium','admin',?,?,?)",
                               (data["targetId"], sub_status if sub_status in ("active", "suspended", "expired") else "canceled", stamp, stamp))
                db.commit()
            r = db.execute("SELECT id,email,name,role,plan,subscription_status,subscription_source,status,created_at FROM users WHERE id=?", (data["targetId"],)).fetchone()
            return dict(id=r[0], email=r[1], name=r[2], role=r[3], plan=r[4], subscriptionStatus=r[5], subscriptionSource=r[6], status=r[7], createdAt=r[8])
        if action == "settings":
            if data.get("values") is not None:
                allowed = {"freeDailyLimit", "premiumDailyLimit", "registrationEnabled", "freePlanFeatures", "premiumPlanFeatures",
                           "freeSavedCapacity", "premiumSavedCapacity", "premiumExtendedExplanations", "premiumPriorityRouting"}
                for key, value in data["values"].items():
                    if key not in allowed: continue
                    db.execute("INSERT INTO platform_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, json.dumps(value), stamp))
                db.commit()
            defaults = {"freeDailyLimit": 100, "premiumDailyLimit": 100, "registrationEnabled": True,
                        "freePlanFeatures": ["Kuniga 100 ta masala", "Matematika va geometriya", "Bosqichma-bosqich yechimlar", "SymPy tekshiruvi", "Rasm orqali masala yechish", "Yechimlarni saqlash"],
                "premiumPlanFeatures": ["Kuniga 100 ta masala", "Kengaytirilgan nazariya", "Barcha matematika va geometriya", "Tezroq AI yo‘naltirish"],
                "freeSavedCapacity": 1000, "premiumSavedCapacity": 1000, "premiumExtendedExplanations": True, "premiumPriorityRouting": True}
            for r in db.execute("SELECT key,value FROM platform_settings").fetchall(): defaults[r["key"]] = json.loads(r["value"])
            return defaults
        if action == "log_request":
            db.execute("INSERT INTO ai_requests(user_id,model,domain,status,latency_ms,error_code,input_type,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (data.get("userId"), data.get("model"), data.get("domain", "math"), data["status"], data["latencyMs"], data.get("errorCode"), data.get("inputType", "text"), stamp)); db.commit(); return True
        if action == "provision_admin":
            email, name, password = data["email"].strip().lower(), data["name"].strip(), data["password"]
            if email != OWNER_ADMIN_EMAIL: raise ValueError("Administrator hisobi faqat platforma egasiga berilishi mumkin.")
            if not re.fullmatch(r"[^\s@]{1,64}@[^\s@.]+(?:\.[^\s@.]+)+", email): raise ValueError("Email manzili noto‘g‘ri.")
            if len(password) < 14: raise ValueError("Admin paroli kamida 14 belgidan iborat bo‘lishi kerak.")
            salt = secrets.token_bytes(16); hashed = __import__("hashlib").scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
            db.execute("INSERT INTO users(email,name,password_hash,password_salt,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET name=excluded.name,password_hash=excluded.password_hash,password_salt=excluded.password_salt,role='admin',status='active',updated_at=excluded.updated_at",
                       (email, name, hashed, salt.hex(), "admin", stamp, stamp)); db.commit(); return True
        raise ValueError("Amal tanilmadi.")
    finally:
        db.close()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "provision-admin":
        email = input("Administrator email: ").strip()
        name = input("Administrator name: ").strip()
        password = getpass.getpass("Administrator password (14+ characters): ")
        confirmation = getpass.getpass("Repeat password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr); raise SystemExit(2)
        print(json.dumps({"ok": True, "result": op({"op": "provision_admin", "email": email, "name": name, "password": password})}))
        return
    data = json.loads(sys.stdin.read() or "{}")
    try:
        print(json.dumps({"ok": True, "result": op(data)}, ensure_ascii=False))
    except PermissionError as exc:
        print(json.dumps({"ok": False, "kind": "permission", "error": str(exc)}, ensure_ascii=False))
    except ValueError as exc:
        print(json.dumps({"ok": False, "kind": "validation", "error": str(exc)}, ensure_ascii=False))
    except Exception:
        print(json.dumps({"ok": False, "kind": "database", "error": "Database operation failed."}))


if __name__ == "__main__":
    main()
