import { getDemoOrder, getDemoOrders } from "@/lib/orders-db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ order_id: string }> }
) {
  try {
    const { order_id } = await params;
    const order = getDemoOrder(order_id);
    if (!order) {
      return Response.json(
        {
          error: `Order ${order_id} was not found. Use one of the exact sample IDs shown in the support panel.`,
          available_order_ids: getDemoOrders().map(({ id }) => id),
        },
        { status: 404 }
      );
    }
    return Response.json(order, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error("Error retrieving order:", error);
    return Response.json({ error: "Error retrieving order" }, { status: 500 });
  }
}
