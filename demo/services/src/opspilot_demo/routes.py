"""What each demo service does. Deliberately small; the telemetry is the point."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from opspilot_demo.downstream import Downstream

logger = logging.getLogger("opspilot_demo")

PRODUCTS = {"mug": 12.0, "tee": 25.0, "sticker": 3.0}


class Item(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=20)


class Order(BaseModel):
    items: list[Item] = Field(min_length=1, max_length=20)


def downstream(request: Request) -> Downstream:
    services: Services = request.app.state.downstream
    return services


Services = Annotated[Downstream, Depends(downstream)]

storefront = APIRouter()
checkout = APIRouter()
payment = APIRouter()
inventory = APIRouter()
notification = APIRouter()


@storefront.get("/api/products")
async def list_products(services: Services) -> object:
    return await services.require("inventory", "GET", "/stock")


@storefront.post("/api/checkout")
async def place_order(order: Order, services: Services) -> object:
    return await services.require("checkout", "POST", "/orders", json=order.model_dump())


@checkout.post("/orders")
async def create_order(order: Order, services: Services) -> dict[str, object]:
    await services.require("inventory", "POST", "/reserve", json=order.model_dump())
    total = sum(PRODUCTS.get(i.sku, 1.0) * i.quantity for i in order.items)
    charge = await services.require("payment", "POST", "/charge", json={"amount": total})
    # Notifications are best effort: an order is never failed because of them.
    try:
        notified = (
            await services.call("notification", "POST", "/notify", json={"amount": total})
        ).is_success
    except HTTPException:
        notified = False
    return {
        "status": "confirmed",
        "total": total,
        "payment": charge["status"],
        "notified": notified,
    }


@payment.post("/charge")
async def charge(body: dict[str, float]) -> dict[str, str]:
    if body.get("amount", 0) <= 0:
        raise HTTPException(422, "amount must be positive")
    return {"status": "approved"}


@inventory.get("/stock")
async def stock() -> dict[str, object]:
    return {
        "items": [{"sku": sku, "price": price, "available": 100} for sku, price in PRODUCTS.items()]
    }


@inventory.post("/reserve")
async def reserve(order: Order) -> dict[str, str]:
    return {"status": "reserved"}


@notification.post("/notify")
async def notify(body: dict[str, float]) -> dict[str, str]:
    logger.info("order notification sent", extra={"service": "notification"})
    return {"status": "sent"}


ROUTERS = {
    "storefront": storefront,
    "checkout": checkout,
    "payment": payment,
    "inventory": inventory,
    "notification": notification,
}
