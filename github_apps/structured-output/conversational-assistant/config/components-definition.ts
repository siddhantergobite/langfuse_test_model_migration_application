// List of components that will be used by the generate_ui tool
// Define recursive components using the $ref property
// More information on supported schemas: https://platform.openai.com/docs/guides/structured-outputs#supported-schemas

export const components = [
  {
    name: 'card',
    parameters: {
      children: {
        type: 'array',
        items: { $ref: '#/$defs/component' }
      }
    }
  },
  {
    name: 'header',
    parameters: {
      content: {
        type: 'string',
        description: 'The text content.'
      }
    }
  },
  {
    name: 'carousel',
    parameters: {
      children: {
        type: 'array',
        items: {
          anyOf: [{ $ref: '#/$defs/item' }, { $ref: '#/$defs/order' }]
        }
      }
    }
  },
  {
    name: 'item',
    parameters: {
      id: {
        type: 'string'
      },
      item_name: {
        type: 'string'
      },
      primary_image: {
        type: 'string'
      },
      description: {
        type: 'string'
      },
      price: {
        type: 'number'
      }
    }
  },
  {
    name: 'order',
    parameters: {
      id: {
        type: 'string',
        description: 'ID of the order.'
      },
      total: {
        type: 'number',
        description: 'Total price of the order.'
      },
      status: {
        type: 'string',
        description: 'Status of the order.'
      },
      date: {
        type: 'string',
        description: 'Date of the order in format YYYY-MM-DD.'
      },
      products: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            item: {
              $ref: '#/$defs/item'
            },
            quantity: {
              type: 'integer',
              description: 'Quantity of the product.'
            }
          },
          required: ['item', 'quantity'],
          additionalProperties: false
        }
      }
    }
  },
  {
    name: 'bar_chart',
    parameters: {
      columns: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            label: {
              type: 'string',
              description: 'Label for the column.'
            },
            value: {
              type: 'string',
              description: 'Value for the column.'
            }
          },
          required: ['label', 'value'],
          additionalProperties: false
        }
      }
    }
  },
  {
    name: 'table',
    parameters: {
      columns: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            key: {
              type: 'string',
              description: 'Key for the column.'
            },
            title: {
              type: 'string',
              description: 'Title for the column.'
            }
          },
          required: ['key', 'title'],
          additionalProperties: false
        }
      },
      rows: {
        type: 'array',
        items: {
          $ref: '#/$defs/row'
        }
      }
    }
  },
  {
    name: 'row',
    parameters: {
      values: {
        type: 'array',
        description:
          'An array of values for the row, either strings or integers.',
        items: {
          anyOf: [{ type: 'string' }, { type: 'integer' }]
        }
      }
    }
  }
]
