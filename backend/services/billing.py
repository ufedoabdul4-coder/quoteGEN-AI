"""Quotation quotas and Flutterwave monthly plan payments."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import HTTPException

from services import supabase_client
from services.context import require_current_user

BILLING_ACCOUNTS = "billing_accounts"
BILLING_PAYMENTS = "billing_payments"
FREE_QUOTATION_LIMIT = 10
FREE_DAILY_LIMIT = 3
FREE_QUOTA_WINDOW_DAYS = 30
FLUTTERWAVE_API = "https://api.flutterwave.com/v3"


def monthly_price_ngn() -> int:
    try:
        price = int(os.environ.get("FLUTTERWAVE_MONTHLY_PRICE_NGN", "13310"))
    except ValueError as error:
        raise RuntimeError("FLUTTERWAVE_MONTHLY_PRICE_NGN must be a whole number.") from error
    if price <= 0:
        raise RuntimeError("FLUTTERWAVE_MONTHLY_PRICE_NGN must be greater than zero.")
    return price


def _client():
    client = supabase_client.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Account billing requires Supabase configuration.")
    return client


def _secret_key() -> str:
    secret = (os.environ.get("FLUTTERWAVE_SECRET_KEY") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Flutterwave payments are not configured yet.")
    return secret


def get_status() -> dict[str, Any]:
    user_id = require_current_user()
    now = datetime.now(timezone.utc)
    result = (
        _client().table(BILLING_ACCOUNTS)
        .select("paid_until")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    account = (result.data or [{}])[0]
    paid_until = account.get("paid_until")
    active = False
    if paid_until:
        active = datetime.fromisoformat(paid_until.replace("Z", "+00:00")) > now

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rolling_start = (now - timedelta(days=FREE_QUOTA_WINDOW_DAYS)).isoformat()
    generated_today = _usage_count(user_id, since=today_start)
    free_today = _usage_count(user_id, since=today_start, free_only=True)
    free_used = _usage_count(user_id, since=rolling_start, free_only=True)
    return {
        "free_limit": FREE_QUOTATION_LIMIT,
        "free_used": free_used,
        "free_remaining": max(0, FREE_QUOTATION_LIMIT - free_used),
        "free_daily_limit": FREE_DAILY_LIMIT,
        "free_used_today": free_today,
        "free_daily_remaining": max(0, FREE_DAILY_LIMIT - free_today),
        "pdfs_generated_today": generated_today,
        "free_quota_window_days": FREE_QUOTA_WINDOW_DAYS,
        "paid_until": paid_until,
        "monthly_plan_active": active,
        "monthly_price_ngn": monthly_price_ngn(),
        "billing_enabled": True,
    }


def _usage_count(user_id: str, *, since: str, free_only: bool = False) -> int:
    query = (
        _client().table("quotation_usage")
        .select("document_id", count="exact", head=True)
        .eq("user_id", user_id)
        .gte("created_at", since)
    )
    if free_only:
        query = query.eq("is_free", True)
    result = query.execute()
    return int(result.count or 0)


def consume_quotation(document_id: str) -> bool:
    result = _client().rpc(
        "consume_quotation",
        {"p_user_id": require_current_user(), "p_document_id": document_id},
    ).execute()
    return bool(result.data)


def create_checkout(email: str, name: str, frontend_url: str) -> str:
    user_id = require_current_user()
    secret = _secret_key()
    price = monthly_price_ngn()
    tx_ref = f"qg-{uuid.uuid4().hex}"
    client = _client()
    client.table(BILLING_PAYMENTS).insert({
        "tx_ref": tx_ref,
        "user_id": user_id,
        "amount_ngn": price,
        "status": "pending",
    }).execute()

    try:
        response = httpx.post(
            f"{FLUTTERWAVE_API}/payments",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            json={
                "tx_ref": tx_ref,
                "amount": str(price),
                "currency": "NGN",
                "redirect_url": f"{frontend_url.rstrip('/')}/?payment=complete",
                "customer": {"email": email, "name": name or email},
                "customizations": {
                    "title": "quoteGEN AI",
                    "description": "One month of unlimited quotations",
                },
            },
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as error:
        client.table(BILLING_PAYMENTS).update({"status": "failed"}).eq("tx_ref", tx_ref).execute()
        raise HTTPException(status_code=502, detail="Could not start the Flutterwave checkout.") from error

    link = (body.get("data") or {}).get("link")
    if body.get("status") != "success" or not isinstance(link, str) or not link.startswith("https://"):
        client.table(BILLING_PAYMENTS).update({"status": "failed"}).eq("tx_ref", tx_ref).execute()
        raise HTTPException(status_code=502, detail="Flutterwave did not return a valid checkout link.")
    return link


def _payment_for_reference(tx_ref: str) -> dict[str, Any]:
    result = (
        _client().table(BILLING_PAYMENTS)
        .select("tx_ref,user_id,amount_ngn,status,transaction_id")
        .eq("tx_ref", tx_ref)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Payment reference not found.")
    return rows[0]


def verify_and_activate(transaction_id: str, tx_ref: str, *, expected_user: str | None = None) -> bool:
    if not transaction_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid Flutterwave transaction ID.")
    payment = _payment_for_reference(tx_ref)
    if expected_user and payment["user_id"] != expected_user:
        raise HTTPException(status_code=404, detail="Payment reference not found.")
    if payment["status"] == "successful":
        if str(payment.get("transaction_id")) != transaction_id:
            raise HTTPException(status_code=409, detail="Payment transaction does not match.")
        return True
    if payment["status"] != "pending":
        raise HTTPException(status_code=400, detail="This payment is not pending.")

    try:
        response = httpx.get(
            f"{FLUTTERWAVE_API}/transactions/{transaction_id}/verify",
            headers={"Authorization": f"Bearer {_secret_key()}"},
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Could not verify the Flutterwave payment.") from error

    transaction = body.get("data") or {}
    try:
        amount = Decimal(str(transaction.get("amount", "0")))
        expected_amount = Decimal(str(payment["amount_ngn"]))
    except InvalidOperation as error:
        raise HTTPException(status_code=502, detail="Flutterwave returned an invalid payment amount.") from error

    if (
        body.get("status") != "success"
        or transaction.get("status") != "successful"
        or str(transaction.get("tx_ref")) != tx_ref
        or transaction.get("currency") != "NGN"
        or amount < expected_amount
    ):
        raise HTTPException(status_code=400, detail="Payment is not successful or does not match the expected amount.")

    result = _client().rpc(
        "activate_monthly_plan",
        {"p_tx_ref": tx_ref, "p_transaction_id": transaction_id},
    ).execute()
    if not result.data:
        raise HTTPException(status_code=409, detail="Payment could not be applied to this account.")
    return True


def process_webhook(payload: dict[str, Any]) -> None:
    event = payload.get("event")
    data = payload.get("data") or {}
    tx_ref = data.get("tx_ref")
    transaction_id = data.get("id")
    if (
        event != "charge.completed"
        or data.get("status") != "successful"
        or not tx_ref
        or transaction_id is None
    ):
        return
    verify_and_activate(str(transaction_id), str(tx_ref))
