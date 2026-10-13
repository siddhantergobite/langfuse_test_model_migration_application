'use client'

import { ResumeValues } from '@/lib/resume'
import React, { useCallback, useState } from 'react'
import ExtractedValues from '@/components/extracted-values'
import FileDropper from '@/components/file-dropper'

const ResumeExtraction: React.FC = () => {
  const [values, setValues] = useState<ResumeValues>()
  const [loading, setLoading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string>()

  const onFileSelected = useCallback(
    (selectedFile: File) => {
      setFile(selectedFile)
      setValues(undefined)
      setError(undefined)
      setLoading(true)

      // Start processing the file
      ;(async () => {
        try {
          const formData = new FormData()
          formData.append('files', selectedFile)

          const response = await fetch('/api/extract_resume', {
            method: 'POST',
            body: formData
          })

          if (!response.ok) {
            const payload = await response.json().catch(() => ({}))
            throw new Error(
              payload.error || `Resume extraction failed (${response.status}).`
            )
          }

          if (!response.body) {
            throw new Error('ReadableStream not supported in this browser.')
          }

          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let done = false
          let partialData = ''

          while (!done) {
            const { value, done: readerDone } = await reader.read()
            done = readerDone
            const chunkValue = decoder.decode(value)
            partialData += chunkValue

            const dataParts = partialData.split('\n')
            partialData = dataParts.pop() || ''

            for (const dataPart of dataParts) {
              if (dataPart.trim() === '') continue
              let parsedData
              try {
                parsedData = JSON.parse(dataPart)
              } catch (e) {
                console.error('Error parsing JSON:', e)
                continue
              }
              if (parsedData.error) throw new Error(parsedData.error)
              setValues(prevValues => ({
                ...prevValues,
                ...parsedData
              }))
            }
          }
          if (partialData.trim()) {
            const parsedData = JSON.parse(partialData)
            if (parsedData.error) throw new Error(parsedData.error)
            setValues(prevValues => ({ ...prevValues, ...parsedData }))
          }
        } catch (error) {
          console.error(
            'Resume extraction failed:',
            error instanceof Error ? error.message : 'Unknown error'
          )
          setError(
            error instanceof Error
              ? error.message
              : 'Resume extraction failed. Check the Parent System request activity.'
          )
        } finally {
          setLoading(false)
        }
      })()
    },
    [setFile, setValues, setLoading]
  )

  return (
    <div className="flex h-screen w-full py-2 px-4 flex-col">
      <div className="size-full flex flex-col sm:flex-row">
        <div className="w-full sm:w-1/2 size-full p-8">
          <FileDropper
            file={file}
            setFile={setFile}
            setValues={setValues}
            onFileSelected={onFileSelected}
          />
        </div>
        <div className="w-full sm:w-1/2 size-full p-8">
          <ExtractedValues values={values} loading={loading} error={error} />
        </div>
      </div>
    </div>
  )
}

export default ResumeExtraction
