// List of tools available to the assistant
// No need to include the top-level wrapper object as it is added in lib/tools/tools.ts
// More information on function calling: https://platform.openai.com/docs/guides/function-calling

export const toolsList = [
  {
    name: 'get_products',
    description: 'Fetch the list of available products',
    parameters: {}
  },
  {
    name: 'get_product_details',
    description: 'Fetch the details of a product',
    parameters: {
      productId: {
        type: 'string',
        description: 'ID of the product to fetch details for'
      }
    }
  },
  {
    name: 'get_orders',
    description: 'Fetch the list of orders',
    parameters: {}
  },
  {
    name: 'file_claim',
    description: 'File a claim on behalf of a customer',
    parameters: {
      orderId: {
        type: 'string',
        description: 'ID of the order to file a claim for'
      },
      reason: {
        type: 'string',
        description: 'Reason for the claim'
      },
      description: {
        type: 'string',
        description: 'Description of the claim'
      }
    }
  },
  {
    name: 'create_return',
    description: 'Create a return for a specific order.',
    parameters: {
      orderId: {
        type: 'string',
        description: 'ID of the order to return'
      },
      return_items: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            productId: {
              type: 'string',
              description: 'ID of the product to return'
            },
            quantity: {
              type: 'integer',
              description: 'Quantity of the product to return'
            }
          },
          required: ['productId', 'quantity'],
          additionalProperties: false
        }
      }
    }
  },
  {
    name: 'add_to_cart',
    description:
      'Add items to cart when the user has confirmed their interest.',
    parameters: {
      items: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            productId: {
              type: 'string',
              description: 'ID of the product to add to the cart'
            },
            quantity: {
              type: 'integer',
              description: 'Quantity of the product to add to the cart'
            }
          },
          required: ['productId', 'quantity'],
          additionalProperties: false
        }
      }
    }
  }
]
