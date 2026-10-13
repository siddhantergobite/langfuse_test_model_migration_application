import { orders } from '@/config/data/demo-data'

export async function GET() {
  try {
    return new Response(JSON.stringify({ orders }), {
      status: 200
    })
  } catch (error) {
    console.error(error)
    return new Response(JSON.stringify({ error: 'Failed to fetch orders' }), {
      status: 500
    })
  }
}
