import { EXTRACT_VALUES_PROMPT, MODEL } from '@/lib/constants'
import { ResumeSchema } from '@/lib/resume'
import { promises as fs } from 'fs'
import { tmpdir } from 'os'
import path from 'path'
import { randomUUID } from 'crypto'
import OpenAI from 'openai'
import { zodResponseFormat } from 'openai/helpers/zod'
import PDFParser from 'pdf2json'

export const runtime = 'nodejs'

function extractValues(resumeText: string): ReadableStream {
  const openai = new OpenAI()
  const stream = openai.beta.chat.completions.stream({
    model: MODEL,
    messages: [
      { role: 'system', content: EXTRACT_VALUES_PROMPT },
      { role: 'user', content: resumeText }
    ],
    response_format: zodResponseFormat(ResumeSchema, 'event')
  })

  const encoder = new TextEncoder()

  const readableStream = new ReadableStream({
    start(controller) {
      let finished = false
      stream
        .on('content.delta', ({ parsed }) => {
          if (finished) return
          try {
            controller.enqueue(encoder.encode(JSON.stringify(parsed) + '\n'))
          } catch {
            finished = true
            stream.abort()
          }
        })
        .on('content.done', () => {
          if (finished) return
          finished = true
          controller.close()
        })
        .on('error', error => {
          if (finished) return
          finished = true
          console.error(
            'Resume extraction provider stream failed:',
            error instanceof Error ? error.name : 'UnknownError'
          )
          try {
            controller.enqueue(
              encoder.encode(
                JSON.stringify({
                  error:
                    'Resume extraction failed. Check the Parent System request activity for the provider error.'
                }) + '\n'
              )
            )
            controller.close()
          } catch {
            // The browser may have cancelled the stream already.
          }
        })
    },
    cancel() {
      stream.abort()
    }
  })

  return readableStream
}

async function parsePDF(uploadedFiles: FormDataEntryValue[]): Promise<string> {
  const uploadedFile = uploadedFiles?.[0]
  if (!(uploadedFile instanceof File)) {
    throw new Error(uploadedFile ? 'Uploaded file is not of type File' : 'No files uploaded')
  }

  // Use the operating system's temp directory so uploads work on Windows and Unix.
  const tempFilePath = path.join(tmpdir(), `resume-${randomUUID()}.pdf`)
  const fileBuffer = Buffer.from(await uploadedFile.arrayBuffer())
  await fs.writeFile(tempFilePath, fileBuffer)

  try {
    return await new Promise((resolve, reject) => {
      const pdfParser = new (PDFParser as any)(null, 1)
      pdfParser.on('pdfParser_dataError', (errData: any) => reject(errData.parserError))
      pdfParser.on('pdfParser_dataReady', () => {
        resolve((pdfParser as any).getRawTextContent())
      })
      pdfParser.loadPDF(tempFilePath)
    })
  } finally {
    await fs.rm(tempFilePath, { force: true })
  }
}

export async function POST(req: Request) {
  try {
    const formData = await req.formData()
    const uploadedFiles = formData.getAll('files')

    const resumeText = await parsePDF(uploadedFiles)

    const readableStream = extractValues(resumeText)

    return new Response(readableStream, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'Transfer-Encoding': 'chunked'
      }
    })
  } catch (error) {
    console.error(
      'Resume extraction request failed:',
      error instanceof Error ? error.name : 'UnknownError'
    )
    return new Response(
      JSON.stringify({
        error:
          'Could not process this resume. Check that the PDF is readable and the Parent System model route is available.'
      }),
      { status: 500 }
    )
  }
}
