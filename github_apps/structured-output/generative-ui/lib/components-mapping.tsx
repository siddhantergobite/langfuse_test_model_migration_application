'use client'
import { componentsMap } from './components'
import React from 'react'

type Component = {
  name: string
  [key: string]: any
}

export const getComponent = (component: Component) => {
  if (!component) return null

  const ComponentToRender =
    componentsMap[component.name as keyof typeof componentsMap]
  if (!ComponentToRender) return null

  return <ComponentToRender {...component} />
}
