import React, { useEffect, useRef } from 'react'

import { getComponent } from '@/lib/components-mapping'
import { Braces, X } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { coy } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface FunctionCallProps {
  functionCall: any
}

const UIDisplay: React.FC<FunctionCallProps> = ({
  functionCall
}: {
  functionCall: any
}) => {
  const [showJSON, setShowJSON] = React.useState(false)

  const toggleShowJSON = () => {
    setShowJSON(!showJSON)
  }

  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'instant' })
  }, [functionCall])

  return (
    <div className="flex justify-center items-center overflow-y-scroll rounded-lg px-8 py-2 h-full w-full">
      {(() => {
        if (functionCall?.name === 'generate_ui') {
          return (
            <div className="w-full relative my-2 h-[70vh]">
              <div
                className="absolute right-4 top-4 z-10"
                onClick={toggleShowJSON}
              >
                {showJSON ? (
                  <X
                    size={20}
                    className="cursor-pointer text-neutral-900 hover:text-neutral-700"
                  />
                ) : (
                  <Braces
                    size={20}
                    className="cursor-pointer text-neutral-900 hover:text-neutral-700"
                  />
                )}
              </div>
              <div
                className={`text-xs max-h-[500px] font-mono overflow-x-scroll h-full w-full overflow-y-scroll rounded-xl ${
                  showJSON ? '' : 'hidden'
                }`}
              >
                <SyntaxHighlighter
                  language="json"
                  style={coy}
                  customStyle={{
                    borderRadius: '0.75rem',
                    paddingTop: '16px',
                    paddingBottom: '16px',
                    marginTop: 0
                  }}
                >
                  {JSON.stringify(functionCall.parsedArguments, null, 2)}
                </SyntaxHighlighter>
              </div>
              <div className="flex items-center justify-center">
                <div
                  className={`${showJSON ? 'hidden' : ''} py-12 h-full w-full`}
                >
                  {getComponent(functionCall.parsedArguments.component) ?? null}
                </div>
                <div ref={endRef} />
              </div>
            </div>
          )
        }
      })()}
    </div>
  )
}

export default UIDisplay
