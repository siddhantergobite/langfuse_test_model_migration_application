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
        description: 'Text content of the header'
      }
    }
  },
  {
    name: 'container',
    parameters: {
      content: {
        type: 'string',
        description: 'Text content of the container'
      },
      classes: {
        type: 'string',
        description:
          'Tailwind classes to apply to the container, empty string if no classes are needed'
      }
    }
  },
  {
    name: 'carousel',
    parameters: {
      children: {
        type: 'array',
        items: {
          anyOf: [{ $ref: '#/$defs/card' }, { $ref: '#/$defs/item' }]
        }
      }
    }
  },
  {
    name: 'item',
    parameters: {
      children: {
        type: 'array',
        items: {
          anyOf: [{ $ref: '#/$defs/header' }, { $ref: '#/$defs/container' }]
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
  }
]
