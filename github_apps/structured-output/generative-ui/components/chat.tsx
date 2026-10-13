'use client'

import React, { useState, useEffect } from 'react'

interface ChatProps {
  onSendMessage: (message: string) => void
  suggestion?: string
}

const Chat: React.FC<ChatProps> = ({ onSendMessage, suggestion }) => {
  const [inputMessageText, setinputMessageText] = useState<string>('')

  // Whenever suggestion changes, update the input field
  useEffect(() => {
    if (suggestion !== undefined) {
      setinputMessageText(suggestion)
    }
  }, [suggestion])

  return (
    <div className="flex w-full flex-col gap-1.5 rounded-[26px] p-1.5 transition-colors bg-white">
      <div className="flex items-center gap-1.5 md:gap-2 pl-4">
        <div className="flex min-w-0 flex-1 flex-col">
          <textarea
            id="prompt-textarea"
            tabIndex={0}
            dir="auto"
            rows={1}
            placeholder="Generate a UI component for..."
            className="m-0 resize-none border-0 focus:outline-none text-sm bg-transparent px-0 py-2 max-h-[20dvh]"
            value={inputMessageText}
            onChange={e => setinputMessageText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onSendMessage(inputMessageText)
                setinputMessageText('')
              }
            }}
          />
        </div>
        <button
          disabled={!inputMessageText}
          data-testid="send-button"
          className="flex size-8 items-center justify-center rounded-full bg-black text-white transition-colors hover:opacity-70 focus-visible:outline-none focus-visible:outline-black disabled:bg-[#D7D7D7] disabled:text-[#f4f4f4] disabled:hover:opacity-100"
          onClick={() => {
            onSendMessage(inputMessageText)
            setinputMessageText('')
          }}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default Chat
