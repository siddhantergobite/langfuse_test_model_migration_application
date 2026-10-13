'use client'

import Chat from '@/components/chat'
import UIDisplay from '@/components/ui-display'
import { PROMPT_SUGGESTIONS } from '@/lib/constants'
import { FunctionCallItem, handleMessage } from '@/lib/handle-message'
import React, { useState, useEffect } from 'react'
import { parse } from 'partial-json'

const MainInterface: React.FC = () => {
  const [functionCall, setFunctionCall] = useState<FunctionCallItem | null>(
    null
  )
  const [suggestion, setSuggestion] = useState<string | undefined>(undefined)
  const [functionArguments, setFunctionArguments] = useState('')

  useEffect(() => {
    if (functionArguments.length > 0) {
      let parsedArguments = {}
      try {
        parsedArguments = parse(functionArguments)
      } catch (e) {
        console.error('Failed to parse arguments:', e)
      }

      setFunctionCall(prev => {
        if (prev) {
          return {
            ...prev,
            arguments: functionArguments,
            parsedArguments
          }
        }
        return null
      })
    }
  }, [functionArguments])

  const onMessage = async (data: any) => {
    const { event: eventType, data: eventData } = data

    if (eventType === 'function_arguments_delta') {
      // Accumulate arguments
      setFunctionArguments(prev => prev + eventData.arguments)

      // If functionCall doesn't exist, create it, otherwise update it
      setFunctionCall(prev => {
        if (!prev) {
          return {
            type: 'function_call',
            status: 'in_progress',
            id: eventData.callId,
            name: eventData.name,
            arguments: eventData.arguments,
            parsedArguments: {},
            output: null
          }
        } else {
          return {
            ...prev,
            status: 'in_progress',
            name: eventData.name,
            id: eventData.callId,
            arguments: prev.arguments + eventData.arguments
          }
        }
      })
    } else if (eventType === 'function_arguments_done') {
      setFunctionArguments(eventData.arguments)
      console.log('functionCall done', functionCall)
      setFunctionCall(prev => {
        if (prev) {
          return { ...prev, status: 'completed' }
        }
        return null
      })
    }
  }

  const handleSendMessage = async (message: string) => {
    setFunctionArguments('')
    setFunctionCall(null)
    if (!message.trim()) return
    await handleMessage(message, onMessage)
    setSuggestion(undefined)
  }

  const applySuggestion = (sugg: string) => {
    setSuggestion(sugg)
  }

  return (
    <div className="flex flex-col justify-bewtween gap-4 w-full h-screen pt-4 px-24 items-center">
      <div className="w-full flex-1 md:w-2/3 flex flex-col items-center justify-center gap-2">
        <Chat onSendMessage={handleSendMessage} suggestion={suggestion} />
        <div className="flex items-center gap-2 py-2 px-4 text-sm overflow-x-scroll w-full pb-4">
          {PROMPT_SUGGESTIONS.map((sugg: string, index: number) => (
            <div
              key={index}
              className="hover:bg-gray-100 cursor-pointer text-sm text-nowrap px-2 py-1 rounded-full border border-gray-300 text-gray-400"
              onClick={() => applySuggestion(sugg)}
            >
              {sugg}
            </div>
          ))}
        </div>
      </div>
      <div className="h-[75vh] w-full bg-gray-50 rounded-t-lg shadow-md md:w-2/3 flex justify-center items-center">
        <UIDisplay functionCall={functionCall} />
      </div>
    </div>
  )
}

export default MainInterface
