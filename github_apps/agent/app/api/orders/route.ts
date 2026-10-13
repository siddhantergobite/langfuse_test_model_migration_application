import { getDemoOrders } from "@/lib/orders-db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return Response.json(getDemoOrders(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error("Error retrieving demo orders:", error);
    return Response.json(
      {
        error: "Error retrieving demo orders",
        detail:
          process.env.NODE_ENV === "development" && error instanceof Error
            ? error.message
            : undefined,
      },
      { status: 500 }
    );
  }
}
