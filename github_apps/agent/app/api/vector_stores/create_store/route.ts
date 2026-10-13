import OpenAI from "openai";

export async function POST(request: Request) {
  const { name } = await request.json();
  try {
    const openai = new OpenAI();
    const vectorStore = await openai.vectorStores.create({
      name,
    });
    console.log("Vector store created:", vectorStore);
    return new Response(JSON.stringify(vectorStore), { status: 200 });
  } catch (error) {
    console.error("Error creating vector store:", error);
    return new Response("Error creating vector store", { status: 500 });
  }
}
