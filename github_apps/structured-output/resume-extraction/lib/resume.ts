import { z } from 'zod'

// Schema used to extract values in a structured way
export const ResumeSchema = z.object({
  name: z.string().optional(),
  title: z.string().optional(),
  location: z.string().optional(),
  contactInfo: z.object({
    email: z.string().optional(),
    website: z.string().optional(),
    linkedin: z.string().optional(),
    twitter: z.string().optional(),
    github: z.string().optional()
  }),
  workExperience: z
    .array(
      z.object({
        startYear: z.string().optional(),
        endYear: z.string().optional(),
        title: z.string().optional(),
        company: z.string().optional(),
        location: z.string().optional(),
        description: z.string().optional()
      }),
      {
        description:
          'Work experience, ordered from the most recent to the oldest.'
      }
    )
    .optional(),
  education: z
    .array(
      z.object({
        startYear: z.string().optional(),
        endYear: z.string().optional(),
        degree: z.string().optional(),
        institution: z.string().optional(),
        location: z.string().optional(),
        description: z.string().optional()
      }),
      {
        description: 'Education, ordered from the most recent to the oldest.'
      }
    )
    .optional(),
  skills: z
    .array(
      z.object({
        name: z.string().optional()
      })
    )
    .optional()
})

export interface ExperienceItem {
  title?: string
  company?: string
  startYear?: string
  endYear?: string
  location?: string
  description?: string
}

export interface EducationItem {
  institution?: string
  degree?: string
  startYear?: string
  endYear?: string
  location?: string
  description?: string
}

export interface Skill {
  name: string
  level?: string
}

export interface ContactInfo {
  email?: string
  phone?: string
  website?: string
  linkedin?: string
  twitter?: string
}

export interface ResumeValues {
  name?: string
  title?: string
  location?: string
  contactInfo?: ContactInfo
  workExperience?: ExperienceItem[]
  education?: EducationItem[]
  skills?: Skill[]
}
