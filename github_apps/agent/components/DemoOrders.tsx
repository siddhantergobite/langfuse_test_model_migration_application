"use client";

import { useEffect, useState } from "react";
import useDataStore from "@/stores/useDataStore";
import type { DemoOrder } from "@/lib/orders-db";

export default function DemoOrders() {
  const customerId = useDataStore((state) => state.customerDetails.id);
  const [orders, setOrders] = useState<DemoOrder[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetch("/api/orders", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Could not load the sample orders.");
        }
        return (await response.json()) as DemoOrder[];
      })
      .then((data) => {
        if (active) {
          setOrders(data.filter((order) => order.customer_id === customerId));
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load the sample orders."
          );
        }
      });

    return () => {
      active = false;
    };
  }, [customerId]);

  return (
    <section className="space-y-2">
      <div>
        <h2 className="text-black text-md font-medium">Sample order IDs</h2>
        <p className="text-xs text-zinc-500">
          Ask about an exact ID such as ORD1008. These records are in the demo database.
        </p>
      </div>
      {error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : orders.length === 0 ? (
        <p className="text-sm text-zinc-500">Loading sample orders…</p>
      ) : (
        <div className="space-y-2">
          {orders.map((order) => (
            <div
              key={order.id}
              className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <code className="font-semibold text-zinc-900">{order.id}</code>
                <span className="capitalize text-zinc-500">{order.status}</span>
              </div>
              <div className="mt-1 text-zinc-700">{order.product}</div>
              <div className="mt-1 text-zinc-500">
                {order.date} · ${order.total.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
