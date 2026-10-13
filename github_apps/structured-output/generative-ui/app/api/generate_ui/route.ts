import OpenAI from 'openai'
import { MODEL, SYSTEM_PROMPT } from '@/lib/constants'
import { generateUITool } from '@/lib/generate-ui-tool'
import {
  ChatCompletionMessageParam,
  ChatCompletionTool
} from 'openai/resources/chat/completions'

const openai = new OpenAI()

const toolsDefinition = [generateUITool]

const tools = toolsDefinition.map(tool => {
  return {
    type: 'function',
    function: {
      ...tool,
      parameters: tool.parameters
    }
  }
})

export async function POST(request: Request) {
  const { user_input } = await request.json()

  try {
    const stream = new ReadableStream({
      async start(controller) {
        try {
          console.log('Starting OpenAI stream', user_input)

          const messages = [
            {
              role: 'system',
              content: SYSTEM_PROMPT
            },
            {
              role: 'user',
              content: user_input
            }
          ] as ChatCompletionMessageParam[]

          const openaiStream = openai.beta.chat.completions.stream({
            model: MODEL,
            messages,
            temperature: 0,
            tools: tools as ChatCompletionTool[],
            //Forcing tool call to generate UI
            tool_choice: {
              type: 'function',
              function: { name: 'generate_ui' }
            },
            parallel_tool_calls: false
          })

          let functionArguments = ''
          let callId = ''
          let functionName = ''
          let isCollectingFunctionArgs = false

          for await (const part of openaiStream) {
            const delta = part.choices[0].delta
            const finishReason = part.choices[0].finish_reason

            if (delta.content) {
              const data = JSON.stringify({
                event: 'assistant_delta',
                data: delta
              })
              controller.enqueue(`data: ${data}\n\n`)
            }

            if (delta.tool_calls) {
              isCollectingFunctionArgs = true
              if (delta.tool_calls[0].id) {
                callId = delta.tool_calls[0].id
              }
              if (delta.tool_calls[0].function?.name) {
                functionName = delta.tool_calls[0].function.name
              }
              functionArguments += delta.tool_calls[0].function?.arguments || ''

              const data = JSON.stringify({
                event: 'function_arguments_delta',
                data: {
                  callId: callId,
                  name: functionName,
                  arguments: delta.tool_calls[0].function?.arguments
                }
              })
              controller.enqueue(`data: ${data}\n\n`)
            }

            if (finishReason === 'tool_calls' && isCollectingFunctionArgs) {
              console.log(`tool call ${functionName} is complete`)
              const data = JSON.stringify({
                event: 'function_arguments_done',
                data: {
                  callId: callId,
                  name: functionName,
                  arguments: functionArguments
                }
              })
              controller.enqueue(`data: ${data}\n\n`)
              functionArguments = ''
              functionName = ''
              isCollectingFunctionArgs = false
            }
          }

          console.log('OpenAI stream done')
          controller.close()
        } catch (error) {
          console.error('Error in stream start:', error)
          controller.error(error)
        }
      }
    })

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive'
      }
    })
  } catch (error: any) {
    console.error('Error in POST handler:', error)
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500
    })
  }
}
