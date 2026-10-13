import { FilePlus2, Trash2 } from 'lucide-react'
import React, { memo, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Document, Page, pdfjs } from 'react-pdf'
import './file-dropper.css'

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

const options = {
  cMapUrl: '/cmaps/',
  standardFontDataUrl: '/standard_fonts/'
}

interface FileDropperProps {
  file: File | null
  setFile: (file: File | null) => void
  setValues: (values: any | null) => void
  onFileSelected: (file: File) => void
}
const FileDropper: React.FC<FileDropperProps> = memo(
  ({ file, setFile, setValues, onFileSelected }) => {
    const onDrop = useCallback(
      (acceptedFiles: File[]) => {
        if (acceptedFiles.length > 0) {
          onFileSelected(acceptedFiles[0])
        }
      },
      [onFileSelected]
    )

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
      onDrop,
      accept: { 'application/pdf': ['.pdf'] },
      multiple: false
    })

    const resetResume = () => {
      setFile(null)
      setValues(null)
    }

    const useExampleFile = () => {
      fetch('/example_resume.pdf')
        .then(response => response.blob())
        .then(blob => {
          const exampleFile = new File([blob], 'example_resume.pdf', {
            type: 'application/pdf'
          })
          onFileSelected(exampleFile)
        })
        .catch(error => {
          console.error('Error fetching the example file:', error)
        })
    }

    return (
      <div className="w-full h-[90vh] flex justify-center items-center">
        {file ? (
          <div className="flex flex-col">
            <div className="document drop-shadow-md mt-4">
              <Document file={file} options={options}>
                <Page className="page" pageNumber={1} scale={0.8} />
              </Document>
            </div>
            <div className="flex justify-center items-center mt-2">
              <div className="text-xs text-neutral-600 mr-2">{file.name}</div>
              <Trash2
                onClick={() => resetResume()}
                size={12}
                className="cursor-pointer text-neutral-800"
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-col justify-center items-center">
            <div
              {...getRootProps()}
              className="p-6 flex items-center justify-center relative focus-visible:outline-0"
            >
              <input {...getInputProps()} />

              <div
                className={`absolute rounded-full transition-all duration-300 ${
                  isDragActive
                    ? 'h-56 w-56 bg-stone-300'
                    : 'h-0 w-0 bg-transparent'
                }`}
              ></div>

              <div className="justify-center flex flex-col items-center text-center z-10 cursor-pointer">
                <FilePlus2 className="mb-4 size-8 text-stone-800" />
                <div className="text-stone-700">Upload a resume</div>
              </div>
            </div>
            <div className="mt-2 text-sm text-stone-500">
              Or{' '}
              <div
                className="inline-block border-b border-stone-400 text-stone-400  cursor-pointer hover:text-stone-500"
                onClick={useExampleFile}
              >
                use the example
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }
)

FileDropper.displayName = 'FileDropper'

export default FileDropper
