export type ScoringStatus = 'Evaluating' | 'Done';
export type InterviewDecision = 'Shortlist' | 'Reject' | 'Hold';

export interface InterviewRecord {
  id: string;
  candidateName: string;
  /** Null for mock rows; the API always sends it. */
  candidateEmail?: string | null;
  requisitionId: string;
  requisitionTitle: string;
  domain: string;
  scoringStatus: ScoringStatus;
  concludedAt: string;
}

export interface TranscriptTurn {
  id: string;
  at: string;
  seconds: number;
  speaker: 'AI' | 'Candidate';
  text: string;
}

export interface RubricAssessment {
  id: string;
  label: string;
  score: number;
  weight: number;
  summary: string;
  reasoning: string;
}

export interface ProctorFrame {
  id: string;
  at: string;
  seconds: number;
  signal: 'Clear' | 'Attention shift' | 'Low light' | 'No face' | 'Multiple faces' | 'Pending';
  /** Presigned snapshot URL when a real proctor image exists. */
  imageUrl?: string;
  /** Whether the vision job has assessed this frame yet. */
  analyzed: boolean;
  /** Vision job's one-line observation, when analyzed. */
  note?: string | null;
}

export type IntegrityVerdict = 'clear' | 'warn' | 'flagged' | 'pending';

export type IntegrityBand = '90-100' | '60-89' | '40-59' | 'under-40';

export interface IntegritySummary {
  verdict: IntegrityVerdict;
  frameCount: number;
  analyzedCount: number;
  signalCounts: Record<string, number>;
  eventCounts: Record<string, number>;
  identityVerdict: string | null;
  /** Final LLM integrity review; null until the review job has run. */
  score: number | null;
  band: IntegrityBand | null;
  summary: string | null;
}

export interface InterviewReview extends InterviewRecord {
  duration: string;
  audioSrc: string;
  finalScore: number;
  percentile: number;
  recommendation: InterviewDecision;
  assessmentSummary: string;
  comparisonScores: number[];
  transcript: TranscriptTurn[];
  // Proctor frames are fetched separately, paginated (useProctorFrames).
  integrity: IntegritySummary | null;
  rubric: RubricAssessment[];
  /** Real recording peaks (0–100 ints) + duration when a recording exists. */
  waveformPeaks?: number[] | null;
  audioDurationSeconds?: number | null;
}

const MOCK_AUDIO_SRC = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

export const MOCK_INTERVIEWS: InterviewRecord[] = [
  { id: 'int-1001', candidateName: 'Ananya Rao', requisitionId: 'ENG-001', requisitionTitle: 'Senior AI Engineer', domain: 'Machine Learning', scoringStatus: 'Done', concludedAt: '2026-07-05T16:42:18' },
  { id: 'int-1002', candidateName: 'Marcus Lee', requisitionId: 'ENG-001', requisitionTitle: 'Senior AI Engineer', domain: 'Machine Learning', scoringStatus: 'Evaluating', concludedAt: '2026-07-05T15:18:44' },
  { id: 'int-1003', candidateName: 'Priya Menon', requisitionId: 'DAT-003', requisitionTitle: 'Data Scientist', domain: 'Data Science', scoringStatus: 'Done', concludedAt: '2026-07-04T19:08:12' },
  { id: 'int-1004', candidateName: 'Ethan Walker', requisitionId: 'DES-042', requisitionTitle: 'Product Designer', domain: 'Product', scoringStatus: 'Done', concludedAt: '2026-07-04T13:25:50' },
  { id: 'int-1005', candidateName: 'Fatima Khan', requisitionId: 'ENG-017', requisitionTitle: 'Frontend Engineer', domain: 'Engineering', scoringStatus: 'Evaluating', concludedAt: '2026-07-03T18:56:06' },
  { id: 'int-1006', candidateName: 'Noah Chen', requisitionId: 'OPS-008', requisitionTitle: 'DevOps Lead', domain: 'Infrastructure', scoringStatus: 'Done', concludedAt: '2026-07-02T11:47:35' },
  { id: 'int-1007', candidateName: 'Meera Iyer', requisitionId: 'PM-005', requisitionTitle: 'Product Manager', domain: 'Product', scoringStatus: 'Done', concludedAt: '2026-07-01T17:15:29' },
  { id: 'int-1008', candidateName: 'Oliver Smith', requisitionId: 'ENG-023', requisitionTitle: 'Backend Engineer', domain: 'Engineering', scoringStatus: 'Evaluating', concludedAt: '2026-06-30T20:33:11' },
  { id: 'int-1009', candidateName: 'Sara Ahmed', requisitionId: 'MKT-011', requisitionTitle: 'Growth Manager', domain: 'Marketing', scoringStatus: 'Done', concludedAt: '2026-06-29T14:02:41' },
  { id: 'int-1010', candidateName: 'Karan Patel', requisitionId: 'DAT-003', requisitionTitle: 'Data Scientist', domain: 'Data Science', scoringStatus: 'Evaluating', concludedAt: '2026-06-28T10:19:07' },
  { id: 'int-1011', candidateName: 'Lina Garcia', requisitionId: 'ENG-017', requisitionTitle: 'Frontend Engineer', domain: 'Engineering', scoringStatus: 'Done', concludedAt: '2026-06-27T16:50:22' },
  { id: 'int-1012', candidateName: 'Dev Sharma', requisitionId: 'ENG-001', requisitionTitle: 'Senior AI Engineer', domain: 'Machine Learning', scoringStatus: 'Done', concludedAt: '2026-06-26T12:36:59' },
];

const BASE_TRANSCRIPT: TranscriptTurn[] = [
  { id: 't-01', at: '00:00', seconds: 0, speaker: 'AI', text: 'Welcome. We will start with a short architecture prompt and then move into tradeoffs.' },
  { id: 't-02', at: '02:10', seconds: 130, speaker: 'Candidate', text: 'I would first clarify latency targets, expected traffic, and where freshness matters before choosing the retrieval path.' },
  { id: 't-03', at: '08:40', seconds: 520, speaker: 'AI', text: 'How would you evaluate answer quality when the ground truth is incomplete?' },
  { id: 't-04', at: '09:25', seconds: 565, speaker: 'Candidate', text: 'I would combine labeled evals with trace inspection, refusal analysis, and production feedback loops grouped by query class.' },
  { id: 't-05', at: '18:00', seconds: 1080, speaker: 'AI', text: 'Talk through one failure mode you would expect in a multi-tenant deployment.' },
  { id: 't-06', at: '18:38', seconds: 1118, speaker: 'Candidate', text: 'The highest risk is data isolation around embeddings and cached context, so I would enforce tenant-scoped indexes and audit retrieval traces.' },
  { id: 't-07', at: '31:15', seconds: 1875, speaker: 'AI', text: 'What would you ship first if the team only had three weeks?' },
  { id: 't-08', at: '31:51', seconds: 1911, speaker: 'Candidate', text: 'I would ship a narrow path with strong observability: ingestion, retrieval, citation grounding, and a review workflow for low-confidence answers.' },
  { id: 't-09', at: '42:18', seconds: 2538, speaker: 'AI', text: 'Thank you. The interview is complete.' },
];

const BASE_RUBRIC: RubricAssessment[] = [
  {
    id: 'r-01',
    label: 'Technical depth',
    score: 88,
    weight: 35,
    summary: 'Strong system design vocabulary and practical evaluation instincts.',
    reasoning: 'The candidate decomposed the architecture into retrieval, generation, telemetry, and isolation concerns. They named concrete metrics and described failure handling without drifting into vague platform language.',
  },
  {
    id: 'r-02',
    label: 'Problem framing',
    score: 91,
    weight: 25,
    summary: 'Asked clarifying questions before proposing a solution.',
    reasoning: 'They surfaced latency, freshness, tenant isolation, and quality constraints early. This improved the proposed design and showed strong prioritization under ambiguity.',
  },
  {
    id: 'r-03',
    label: 'Communication',
    score: 84,
    weight: 20,
    summary: 'Clear and structured, with a few dense explanations.',
    reasoning: 'The responses were concise and generally easy to follow. Some sections used heavy implementation shorthand, but the candidate corrected course when prompted.',
  },
  {
    id: 'r-04',
    label: 'Execution judgment',
    score: 86,
    weight: 20,
    summary: 'Favored staged delivery and observability over overbuilding.',
    reasoning: 'Their three-week plan focused on a narrow production path, measurable quality gates, and review workflows. That is a good signal for senior execution in an applied AI team.',
  },
];

const REVIEW_OVERRIDES: Partial<Record<string, Partial<InterviewReview>>> = {
  'int-1001': {
    finalScore: 88,
    percentile: 91,
    recommendation: 'Shortlist',
    assessmentSummary: 'Senior-level signal. Strong architecture judgment, grounded evaluation strategy, and clear ownership instincts.',
  },
  'int-1002': {
    finalScore: 73,
    percentile: 58,
    recommendation: 'Hold',
    assessmentSummary: 'Promising, but the score is still being finalized. Current signal is strongest in fundamentals and weaker in production tradeoffs.',
  },
  'int-1003': {
    finalScore: 82,
    percentile: 77,
    recommendation: 'Shortlist',
    assessmentSummary: 'Good modeling judgment and solid communication. Needs a deeper ML ops follow-up before final loop.',
  },
  'int-1004': {
    finalScore: 79,
    percentile: 70,
    recommendation: 'Hold',
    assessmentSummary: 'Strong product critique and portfolio fluency, with moderate evidence around systems collaboration.',
  },
};

function buildReview(record: InterviewRecord, index: number): InterviewReview {
  const score = Math.max(61, 91 - index * 3);
  const override = REVIEW_OVERRIDES[record.id];

  return {
    ...record,
    duration: `${42 - (index % 5)}m ${String(18 + index * 3).padStart(2, '0')}s`,
    audioSrc: MOCK_AUDIO_SRC,
    finalScore: score,
    percentile: Math.max(44, 93 - index * 5),
    recommendation: score >= 84 ? 'Shortlist' : score < 70 ? 'Reject' : 'Hold',
    assessmentSummary: 'Automated assessment synthesized from the transcript, rubric evidence, and interview metadata.',
    comparisonScores: [54, 61, 66, 71, 75, 79, 82, 86, 89, 92, 95],
    transcript: BASE_TRANSCRIPT,
    integrity: null,
    rubric: BASE_RUBRIC.map(item => ({
      ...item,
      score: Math.max(58, Math.min(96, item.score - index * 2)),
    })),
    ...override,
  };
}

export const MOCK_INTERVIEW_REVIEWS: InterviewReview[] = MOCK_INTERVIEWS.map(buildReview);

export function getInterviewReview(id: string | undefined) {
  return MOCK_INTERVIEW_REVIEWS.find(interview => interview.id === id);
}
