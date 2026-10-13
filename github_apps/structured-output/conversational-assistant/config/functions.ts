// Functions mapping to tool calls
// Define one function per tool call - each tool call should have a matching function
// Parameters for a tool call are passed as an object to the corresponding function

export const get_products = async () => {
  const response = await fetch('/api/tools/get_products', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  const result = await response.json()
  return result
}

export const get_product_details = async ({
  productId
}: {
  productId: string
}) => {
  const response = await fetch(
    `/api/tools/get_product_details?productId=${productId}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    }
  )
  const result = await response.json()
  return result
}

export const get_orders = async () => {
  const response = await fetch('/api/tools/get_orders', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  const result = await response.json()
  return result
}

export const create_return = ({
  orderId,
  items
}: {
  orderId: string
  items: any
}) => {
  return {
    message: `Successfully created return for order ${orderId} with items: ${JSON.stringify(
      items
    )}`
  }
}

export const file_claim = ({
  orderId,
  reason,
  description
}: {
  orderId: string
  reason: string
  description: string
}) => {
  return {
    message: `Successfully filed claim for order ${orderId} (reason: ${reason}, description: ${description})`
  }
}

export const add_to_cart = ({ items }: { items: any }) => {
  return {
    message: `Added these items to cart: ${JSON.stringify(items)}`
  }
}

export const functionsMap = {
  get_products,
  get_product_details,
  get_orders,
  file_claim,
  create_return,
  add_to_cart
  // Add more functions here as you define them
}
