import { productDetails } from '@/config/data/demo-data'

export async function GET(request: Request) {
  try {
    const url = new URL(request.url)
    const productId = url.searchParams.get('productId')

    const product = productDetails.find(product => product.id === productId)
    return new Response(JSON.stringify({ product }), {
      status: 200
    })
  } catch (error) {
    console.error(error)
    return new Response(JSON.stringify({ error: 'Failed to find product' }), {
      status: 500
    })
  }
}
