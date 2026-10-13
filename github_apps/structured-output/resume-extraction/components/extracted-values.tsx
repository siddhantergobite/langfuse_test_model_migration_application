import React, { useState } from 'react'

import {
  EducationItem,
  ExperienceItem,
  ResumeValues,
  Skill as SkillInterface
} from '@/lib/resume'
import { Braces, ChevronDown, ChevronRight, X } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { coy } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface ExtractedValuesProps {
  values: ResumeValues | undefined
  loading: boolean
  error?: string
}
const ExtractedValues: React.FC<ExtractedValuesProps> = ({
  values,
  loading,
  error
}: ExtractedValuesProps) => {
  const [showJSON, setShowJSON] = useState(false)
  const toggleShowJSON = () => {
    setShowJSON(!showJSON)
  }

  return (
    <div className="relative h-full w-full">
      <div className="absolute right-4 top-4 z-10" onClick={toggleShowJSON}>
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
      <div className="bg-white p-8 text-stone-900 h-full overflow-y-scroll rounded-xl">
        {error ? (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        ) : null}
        <div
          className={`text-sm font-mono overflow-x-scroll h-full overflow-y-scroll rounded-xl ${
            showJSON ? 'h-full' : 'hidden'
          }`}
        >
          {values ? (
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
              {JSON.stringify(values, null, 2)}
            </SyntaxHighlighter>
          ) : (
            <div className="text-gray-500 text-center mt-6">
              Upload a resume to see the extracted JSON.
            </div>
          )}
        </div>
        <div className={` ${showJSON ? 'hidden' : ''}`}>
          {/* HEADER */}
          <div className="min-h-[100px]">
            {!values?.name ? (
              <div
                className={`h-8 w-48 rounded-md bg-stone-100 ${
                  loading ? 'animate-pulse' : ''
                }`}
              ></div>
            ) : (
              <h2 className="text-lg font-medium text-gray-800">
                {values.name}
              </h2>
            )}
            {!values?.title ? (
              <div
                className={`h-6 w-96 rounded-md bg-stone-100 ${
                  loading ? 'animate-pulse' : ''
                } mt-2`}
              ></div>
            ) : (
              <h3 className="text-gray-600">{values.title}</h3>
            )}
            <div className="flex items-center mt-2">
              {!values?.location ? (
                <>
                  <div
                    className={`h-6 w-28 rounded-md bg-stone-100 ${
                      loading ? 'animate-pulse' : ''
                    } mt-2`}
                  ></div>
                </>
              ) : (
                <div className="text-gray-500 text-xs">{values.location}</div>
              )}
            </div>
          </div>
          {/* CONTACT */}
          <div className="mt-4 text-xs min-h-[100px]">
            <CategoryTitle title="Contact" />
            {!values?.contactInfo ? (
              <>
                {[...Array(3)].map((_, index) => (
                  <div key={index} className="flex items-center">
                    <div
                      className={`h-6 w-28 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                    <div
                      className={`h-6 w-72 ml-2 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                  </div>
                ))}
              </>
            ) : (
              Object.entries(values.contactInfo || {}).map(
                ([key, value]) =>
                  value && (
                    <LabeledValue
                      key={key}
                      label={key.charAt(0).toUpperCase() + key.slice(1)}
                      value={value}
                    />
                  )
              )
            )}
          </div>
          <Divider />
          {/* WORK EXPERIENCE */}
          <div className="mt-6 min-h-[100px]">
            <CategoryTitle title="Work Experience" />
            {!values?.workExperience ? (
              <>
                {[...Array(2)].map((_, index) => (
                  <div key={index} className="flex items-center">
                    <div
                      className={`h-6 w-28 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                    <div
                      className={`h-6 w-72 ml-2 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                  </div>
                ))}
              </>
            ) : (
              values.workExperience.map((experience, index) => (
                <WorkExperience key={index} experience={experience} />
              ))
            )}
          </div>
          <Divider />
          {/* EDUCATION */}
          <div className="mt-6 min-h-[100px]">
            <CategoryTitle title="Education" />

            {!values?.education ? (
              <>
                {[...Array(2)].map((_, index) => (
                  <div key={index} className="flex items-center">
                    <div
                      className={`h-6 w-28 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                    <div
                      className={`h-6 w-72 ml-2 rounded-md bg-stone-100 ${
                        loading ? 'animate-pulse' : ''
                      } mt-2`}
                    ></div>
                  </div>
                ))}
              </>
            ) : (
              values.education.map((experience, index) => (
                <Education key={index} experience={experience} />
              ))
            )}
          </div>
          <Divider />

          {/* SKILLS */}
          <div className="mt-6">
            <CategoryTitle title="Skills" />
            <div className="flex w-full">
              <div className="flex gap-2 flex-wrap">
                {!values?.skills ? (
                  <>
                    {[...Array(6)].map((_, index) => (
                      <div
                        key={index}
                        className={`flex text-xs px-3 py-1 rounded-full bg-stone-100 text-gray-800 mr-1 w-16 h-6 ${
                          loading ? 'animate-pulse' : ''
                        }`}
                      ></div>
                    ))}
                  </>
                ) : (
                  values.skills.map((skill, index) => (
                    <Skill key={index} skill={skill} />
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const LabeledValue: React.FC<{ label: string; value: string }> = ({
  label,
  value
}) => {
  return (
    <div className="flex">
      <div className="w-28 mt-2 text-gray-500 font-light">{label}</div>
      <div className="mt-2 text-gray-700">{value}</div>
    </div>
  )
}

const CategoryTitle: React.FC<{ title: string }> = ({ title }) => {
  return <div className="font-medium text-sm mb-3">{title}</div>
}

const Divider: React.FC = () => {
  return <div className="border-b border-gray-200 my-6"></div>
}

const WorkExperience: React.FC<{ experience: ExperienceItem }> = ({
  experience
}) => {
  const [isDescriptionVisible, setIsDescriptionVisible] = useState(false)

  const toggleDescription = () => {
    setIsDescriptionVisible(!isDescriptionVisible)
  }

  return (
    <div className="flex items-start text-xs mb-4">
      {!experience?.startYear ? (
        <div className={`h-6 w-28 rounded-md bg-stone-100 mt-2`}></div>
      ) : (
        <div className="text-gray-500 min-w-28">
          <span>{experience.startYear}</span> -{' '}
          <span>{experience?.endYear || 'now'}</span>
        </div>
      )}
      {!experience?.title ? (
        <div className={`h-6 w-72 ml-2 rounded-md bg-stone-100 mt-2`}></div>
      ) : (
        <div className="text-gray-800 flex flex-col items-start min-w-96 overflow-x-clip">
          <div className="flex items-center pb-1 text-nowrap">
            <div>{`${experience.title} at `}</div>
            <div className="border-b border-gray-800 ml-1 text-nowrap">
              {experience.company}
            </div>
            {experience.location && (
              <div className="text-gray-500 ml-1">({experience.location})</div>
            )}
            <div
              onClick={toggleDescription}
              className="ml-2 cursor-pointer text-gray-400"
            >
              {isDescriptionVisible ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )}
            </div>
          </div>

          {isDescriptionVisible && experience.description && (
            <div className="text-gray-700 mt-1 text-xs font-light">
              {experience.description}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const Education: React.FC<{ experience: EducationItem }> = ({ experience }) => {
  const [isDescriptionVisible, setIsDescriptionVisible] = useState(false)

  const toggleDescription = () => {
    setIsDescriptionVisible(!isDescriptionVisible)
  }

  return (
    <div className="flex items-start text-xs mb-4">
      <div className="text-gray-500 min-w-28">
        {experience.startYear} - {experience.endYear || 'now'}
      </div>
      <div className="text-gray-800 flex flex-col items-start max-w-[500px] overflow-x-clip">
        <div className="flex items-center pb-1  text-nowrap">
          <div>{`${
            experience.degree && experience.institution
              ? experience.degree + ' at '
              : experience.degree || ''
          }`}</div>
          {experience.institution && (
            <div className="border-b border-gray-800 ml-1 text-nowrap">
              {experience.institution}
            </div>
          )}
          {experience.location && (
            <div className="text-gray-500 ml-1">({experience.location})</div>
          )}
          {experience.description && (
            <div
              onClick={toggleDescription}
              className="ml-2 cursor-pointer text-gray-400"
            >
              {isDescriptionVisible ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )}
            </div>
          )}
        </div>

        {isDescriptionVisible && experience.description && (
          <div className="text-gray-700 mt-1 text-xs font-light">
            {experience.description}
          </div>
        )}
      </div>
    </div>
  )
}

const Skill: React.FC<{ skill: SkillInterface }> = ({ skill }) => {
  return (
    <div className="flex text-xs py-1 px-2 rounded-full bg-stone-100 text-nowrap text-gray-800 h-6">
      <div>{skill.name}</div>
    </div>
  )
}

export default ExtractedValues
