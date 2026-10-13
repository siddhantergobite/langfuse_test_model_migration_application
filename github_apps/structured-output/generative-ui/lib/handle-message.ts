export interface MessageItem {
  type: 'message'
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface FunctionCallItem {
  type: 'function_call'
  status: 'in_progress' | 'completed' | 'failed'
  id: string
  name: string
  arguments: string
  parsedArguments: any
  output: string | null
}

export type Item = MessageItem | FunctionCallItem

export const handleMessage = async (
  user_input: string,
  onMessage: (data: any) => void
) => {
  console.log('Handle message', user_input)
  try {
    const response = await fetch('/api/generate_ui', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ user_input })
    })

    if (!response.ok) {
      console.error(`Error: ${response.statusText}`)
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let done = false
    let buffer = ''

    while (!done) {
      const { value, done: doneReading } = await reader.read()
      done = doneReading
      const chunkValue = decoder.decode(value)
      buffer += chunkValue

      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (dataStr === '[DONE]') {
            done = true
            break
          }
          const data = JSON.parse(dataStr)
          onMessage(data)
        }
      }
    }

    // Handle any remaining data in buffer
    if (buffer && buffer.startsWith('data: ')) {
      const dataStr = buffer.slice(6)
      if (dataStr !== '[DONE]') {
        const data = JSON.parse(dataStr)
        onMessage(data)
      }
    }
  } catch (error) {
    console.error('Error handling turn:', error)
  }
}
