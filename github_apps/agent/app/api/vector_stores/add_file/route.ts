import OpenAI from "openai";

export async function POST(request: Request) {
  const { vectorStoreId, fileId, attributes } = await request.json();
  console.log(
    `Adding file ${fileId} with attributes ${JSON.stringify(attributes)}`
  );
  try {
    const openai = new OpenAI();
    const vectorStore = await openai.vectorStores.files.create(vectorStoreId, {
      file_id: fileId,
      attributes,
    });
    return new Response(JSON.stringify(vectorStore), { status: 200 });
  } catch (error) {
    console.error("Error adding file:", error);
    return new Response("Error adding file", { status: 500 });
  }
}
