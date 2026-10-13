import { CUSTOMER_DETAILS } from "@/config/demoData";
import { getDemoOrders } from "@/lib/orders-db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ user_id: string }> }
) {
  try {
    const { user_id } = await params;
    if (user_id !== CUSTOMER_DETAILS.id) {
      return Response.json({ error: "Customer not found" }, { status: 404 });
    }
    return Response.json(getDemoOrders(user_id), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error("Error retrieving order history:", error);
    return Response.json({ error: "Error retrieving order history" }, { status: 500 });
  }
}
