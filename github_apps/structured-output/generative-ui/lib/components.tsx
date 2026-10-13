// Components that will be used by the generate_ui tool

import React from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { ChartConfig, ChartContainer } from '@/components/ui/chart'
import { getComponent } from './components-mapping'

// Utility Functions
const formatKey = (key: string) =>
  key.toLowerCase().replace(/[^a-zA-Z0-9]/g, '_')

const getChartConfig = (columns: { label: string; value: number }[]) => {
  const config: ChartConfig = {}

  columns.forEach((item: { label: string; value: number }) => {
    config[formatKey(item.label)] = {
      label: item.label,
      color: '#ffffff'
    }
  })

  return config
}

// Chart Data Functions
const getChartData = (columns: { label?: string; value?: string }[]) => {
  return columns
    .filter(item => !!item.label)
    .map((item: { label?: string; value?: string }, index: number) => {
      if (!item.label) {
        throw new Error('Label is required')
      }
      return {
        id: index,
        label: item.label,
        value: item.value !== undefined ? parseFloat(item.value) : 0,
        fill: '#000000'
      }
    })
}

export const CardComponent = ({ children }: { children?: any[] }) => (
  <div className="flex flex-col w-full bg-white rounded-lg p-4 shadow-md my-2 min-w-52">
    {children ? (
      <div className="flex flex-col gap-4">
        {children.map((child: any, index: number) => (
          <React.Fragment key={index}>{getComponent(child)}</React.Fragment>
        ))}
      </div>
    ) : null}
  </div>
)

export const CarouselComponent = ({ children }: { children?: any[] }) => (
  <div className="flex gap-2 overflow-x-scroll w-full">
    {children
      ? children.map((child: any, index: number) => (
          <React.Fragment key={index}>{getComponent(child)}</React.Fragment>
        ))
      : null}
  </div>
)

export const HeaderComponent = ({ content }: { content?: string }) => {
  return (
    <div>
      <h1 className="text-sm text-stone-900 font-medium">{content}</h1>
    </div>
  )
}

export const ContainerComponent = ({
  content,
  classes
}: {
  content?: string
  classes?: string
}) => {
  return <div className={classes}>{content}</div>
}

export const BarChartComponent = ({
  columns
}: {
  columns?: { label?: string; value?: string }[]
}) => {
  if (!columns) return null
  const chartData = getChartData(columns)
  const chartConfig = getChartConfig(chartData)
  return (
    <ChartContainer config={chartConfig}>
      <BarChart accessibilityLayer data={chartData}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="label"
          tickLine={false}
          tickMargin={10}
          axisLine={false}
          padding={{ left: 10, right: 10 }}
        />
        <YAxis orientation="left" width={48} />
        <Bar dataKey="value" fill="#1A535C" radius={6} barSize={30} />
      </BarChart>
    </ChartContainer>
  )
}

export const TableComponent = ({
  columns,
  rows
}: {
  columns?: { key?: string; title?: string }[]
  rows?: any[]
}) => (
  <Table>
    <TableHeader>
      <TableRow>
        {columns?.map((column, index) => (
          <TableHead key={index}>{column.title}</TableHead>
        ))}
      </TableRow>
    </TableHeader>
    <TableBody>
      {rows?.map((row, index) => (
        <TableRow key={index}>
          {row.values?.map((value: string, index: number) => (
            <TableCell key={index}>{value}</TableCell>
          ))}
        </TableRow>
      ))}
    </TableBody>
  </Table>
)

// Components Map
export const componentsMap: Record<string, React.FC<any>> = {
  card: CardComponent,
  carousel: CarouselComponent,
  header: HeaderComponent,
  container: ContainerComponent,
  bar_chart: BarChartComponent,
  table: TableComponent
  // Add more components as you define them in components-definition.ts
}
