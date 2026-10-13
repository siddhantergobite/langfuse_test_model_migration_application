import { products } from '@/config/data/demo-data'

export async function GET() {
  try {
    return new Response(JSON.stringify({ products }), {
      status: 200
    })
  } catch (error) {
    console.error(error)
    return new Response(JSON.stringify({ error: 'Failed to fetch products' }), {
      status: 500
    })
  }
}
