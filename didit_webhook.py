from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime
import requests
import os

# Telegram bot token + admin chat ID
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# DB path
DB_PATH = "buybot.db"

app = Flask(__name__)

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def update_kyc_status(user_id, status):
    now = datetime.utcnow().isoformat()
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE buy_users
        SET kyc_status = ?,
            kyc_completed_at = ?,
            updated_at = ?
        WHERE user_id = ?;
    """, (status, now, now, user_id))

    conn.commit()
    conn.close()

def notify_user(user_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": user_id, "text": message})

def notify_admin(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message})

@app.route("/didit-webhook", methods=["POST"])
def didit_webhook():
    data = request.json
    print("Received webhook:", data)

    # Try all possible locations for Didit fields
    user_id = (
        data.get("reference_id")
        or data.get("user_id")
        or data.get("id")
        or data.get("data", {}).get("reference_id")
        or data.get("data", {}).get("user_id")
        or data.get("data", {}).get("id")
    )

    status = (
        data.get("status")
        or data.get("event")
        or data.get("data", {}).get("status")
        or data.get("data", {}).get("event")
    )

    if not user_id or not status:
        # Return 200 so Didit stops retrying
        return jsonify({"message": "Received but missing fields"}), 200

    # Normalize status
    if status.startswith("verification."):
        status = status.replace("verification.", "")

    update_kyc_status(user_id, status)

    if status == "completed":
        notify_user(user_id, "Your KYC verification is complete.")
    elif status == "failed":
        notify_user(user_id, "Your KYC verification failed. Please try again.")
    elif status == "rejected":
        notify_user(user_id, "Your KYC verification was rejected. Contact support.")

    notify_admin(f"KYC update for user {user_id}: {status}")

    return jsonify({"message": "Webhook processed"}), 200

    # Extract external_user_id (Telegram user ID)
    user_id = data.get("external_user_id")
    status = data.get("status")  # approved / rejected / failed

    if not user_id or not status:
        return jsonify({"error": "Missing fields"}), 400

    # Update DB
    update_kyc_status(user_id, status)

    # Notify user
    if status == "approved":
        notify_user(user_id, "🎉 Your verification has been approved! You can now use the service.")
    elif status == "rejected":
        notify_user(user_id, "❌ Your verification was rejected. Please contact support.")
    else:
        notify_user(user_id, "⚠️ Verification failed. Please try again.")

    # Notify admin
    notify_admin(f"🔔 KYC update for user {user_id}: {status}")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
