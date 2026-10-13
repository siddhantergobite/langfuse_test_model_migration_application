// Placeholder demo data - used in the API routes

import { Order, Product, ProductDetails } from './types'

export const products: Product[] = [
  {
    id: 'qt-24X553',
    name: 'AI-Titan Quantum Processor',
    price: 1590.0,
    description:
      "The AI-Titan Quantum Processor is engineered for next-generation artificial intelligence tasks. Featuring 256 quantum cores and neural acceleration, it's the ideal choice for cutting-edge AI models.",
    image: 'qt-24X553.webp',
    weight: 0.6,
    dimensions: '12cm x 10cm x 2cm'
  },
  {
    id: 'mb-NE9000',
    name: 'Neuronix-9000 AI Motherboard',
    price: 1199.99,
    description:
      'A state-of-the-art AI-focused motherboard featuring integrated neural networking, 12 PCIe 5.0 slots, and optimized heat dissipation for long training cycles.',
    image: 'mb-NE9000.webp',
    weight: 1.8,
    dimensions: '30cm x 25cm x 3cm'
  },
  {
    id: 'acc-MLC82',
    name: 'HyperSynapse ML Accelerator Chip',
    price: 799.99,
    description:
      'Boost your AI training speeds with the HyperSynapse ML Accelerator Chip. It offers lightning-fast matrix computations and supports multi-GPU integrations.',
    image: 'acc-MLC82.webp',
    weight: 0.2,
    dimensions: '5cm x 5cm x 1cm'
  },
  {
    id: 'cl-CE7902',
    name: 'CryoEngine Cooling Module',
    price: 499.99,
    description:
      'A state-of-the-art liquid-cooling system designed specifically for AI hardware. Keep your CPUs, GPUs, and motherboards running at peak efficiency during extended training sessions.',
    image: 'cl-CE7902.webp',
    weight: 2.0,
    dimensions: '25cm x 20cm x 10cm'
  }
]

export const productDetails: ProductDetails[] = [
  {
    id: 'qt-24X553',
    features: [
      '256 Quantum Cores',
      'Neural Acceleration Technology',
      'Energy Efficient Design',
      'Optimized for AI Workloads'
    ],
    warranty: '3 years limited warranty',
    ratings: 4.8,
    release_date: '2024-01-15'
  },
  {
    id: 'mb-NE9000',
    features: [
      'Integrated Neural Networking',
      '12 PCIe 5.0 Slots',
      'Optimized Heat Dissipation',
      'Supports AI Training Hardware'
    ],
    warranty: '3 years limited warranty',
    ratings: 4.7,
    release_date: '2024-08-02'
  },
  {
    id: 'acc-MLC82',
    features: [
      'Lightning-Fast Matrix Computations',
      'Multi-GPU Integration Support',
      'Compact and Efficient Design',
      'Optimized for Machine Learning'
    ],
    warranty: '2 years limited warranty',
    ratings: 4.6,
    release_date: '2024-03-05'
  },
  {
    id: 'cl-CE7902',
    features: [
      'Advanced Liquid Cooling System',
      'High Efficiency Thermal Management',
      'Supports CPUs and GPUs',
      'Quiet and Durable Operation'
    ],
    warranty: '3 years limited warranty',
    ratings: 4.5,
    release_date: '2024-04-04'
  }
]

const daysAgo = (days: number) => {
  const date = new Date(Date.now() - days * 24 * 60 * 60 * 1000)
  return date.toLocaleDateString()
}

export const orders: Order[] = [
  {
    id: 'CX2312',
    items: [
      {
        product: products[0],
        quantity: 1
      },
      {
        product: products[2],
        quantity: 1
      }
    ],
    status: 'delivered',
    created_at: daysAgo(4),
    total: 2389.99
  },
  {
    id: 'CYE223',
    items: [
      {
        product: products[1],
        quantity: 1
      }
    ],
    status: 'cancelled',
    created_at: daysAgo(18),
    total: 1199.99
  },
  {
    id: 'EB2134',
    items: [
      {
        product: products[3],
        quantity: 2
      }
    ],
    status: 'delivered',
    created_at: daysAgo(42),
    total: 999.98
  }
]
