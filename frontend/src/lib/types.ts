export type ApplicationType = 'internship' | 'scholarship' | 'fellowship' | 'research' | 'grant'

export type ApplicationStatus =
  | 'discovered' | 'shortlisted' | 'drafting' | 'ready' | 'applied'
  | 'applied_confirmed' | 'recruiter_engaged' | 'phone_screen' | 'technical_interview'
  | 'onsite' | 'offer' | 'accepted' | 'declined' | 'rejected' | 'ghosted' | 'missed_deadline'

export type ApplicationPriority = 'top_target' | 'standard' | 'longshot'

export interface JdParsed {
  inferred_organization: string
  inferred_role: string
  inferred_type: ApplicationType
  required_skills: string[]
  nice_to_haves: string[]
  seniority: string
  location: string
  compensation: string
  keywords: string[]
  summary: string
}

export interface Application {
  id: string
  type: ApplicationType
  organization: string
  role_or_program: string
  posting_url: string | null
  deadline: string | null
  status: ApplicationStatus
  priority: ApplicationPriority | null
  jd_text: string | null
  jd_parsed: JdParsed | null
  match_score: number | null
  match_explanation: string | null
  notes: string | null
  created_at: string
  updated_at: string
}
