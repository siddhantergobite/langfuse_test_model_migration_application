export interface Product {
  id: string
  name: string
  price: number
  description: string
  image: string
  weight: number
  dimensions: string
}

export interface ProductDetails {
  id: string
  features: string[]
  warranty: string
  ratings: number
  release_date: string
}

export interface OrderItem {
  product: Product
  quantity: number
}

export interface Order {
  id: string
  items: OrderItem[]
  status: 'pending' | 'shipped' | 'delivered' | 'cancelled' | 'returned'
  created_at: string
  total: number
}
