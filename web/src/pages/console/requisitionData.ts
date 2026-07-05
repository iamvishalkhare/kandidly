export interface Requisition {
  id: string;
  code: string;
  title: string;
  domain: string;
  technicalRequirements: string[];
  interviewToken: string;
  openDate: string;
  closeDate: string;
  clicks: number;
  completed: number;
  live: boolean;
}

export const MOCK_REQUISITIONS: Requisition[] = [
  {
    id: 'req-1', code: 'ENG-001', title: 'Senior AI Engineer',
    domain: 'Machine Learning', technicalRequirements: ['Python', 'PyTorch', 'RAG', 'Vector DBs'],
    interviewToken: 'eng-001-senior-ai',
    openDate: '24/05/2026', closeDate: '15/07/2026',
    clicks: 142, completed: 12, live: true,
  },
  {
    id: 'req-2', code: 'DES-042', title: 'Product Designer',
    domain: 'Product', technicalRequirements: ['Figma', 'Design Systems', 'Prototyping'],
    interviewToken: 'des-042-product-designer',
    openDate: '28/05/2026', closeDate: 'N/A',
    clicks: 89, completed: 4, live: true,
  },
  {
    id: 'req-3', code: 'MKT-011', title: 'Growth Manager',
    domain: 'Marketing', technicalRequirements: ['GA4', 'SQL', 'Lifecycle Automation'],
    interviewToken: 'mkt-011-growth-manager',
    openDate: '10/04/2026', closeDate: '01/06/2026',
    clicks: 210, completed: 0, live: false,
  },
  {
    id: 'req-4', code: 'ENG-017', title: 'Frontend Engineer',
    domain: 'Engineering', technicalRequirements: ['React', 'TypeScript', 'Accessibility'],
    interviewToken: 'eng-017-frontend',
    openDate: '02/06/2026', closeDate: 'N/A',
    clicks: 67, completed: 8, live: true,
  },
  {
    id: 'req-5', code: 'DAT-003', title: 'Data Scientist',
    domain: 'Data Science', technicalRequirements: ['Python', 'SQL', 'Forecasting', 'ML Ops'],
    interviewToken: 'dat-003-data-scientist',
    openDate: '15/05/2026', closeDate: '30/07/2026',
    clicks: 195, completed: 15, live: true,
  },
  {
    id: 'req-6', code: 'OPS-008', title: 'DevOps Lead',
    domain: 'Infrastructure', technicalRequirements: ['Kubernetes', 'Terraform', 'AWS', 'CI/CD'],
    interviewToken: 'ops-008-devops-lead',
    openDate: '01/03/2026', closeDate: '15/05/2026',
    clicks: 312, completed: 0, live: false,
  },
  {
    id: 'req-7', code: 'ENG-023', title: 'Backend Engineer',
    domain: 'Engineering', technicalRequirements: ['Node.js', 'PostgreSQL', 'API Design'],
    interviewToken: 'eng-023-backend',
    openDate: '18/06/2026', closeDate: 'N/A',
    clicks: 34, completed: 2, live: true,
  },
  {
    id: 'req-8', code: 'PM-005', title: 'Product Manager',
    domain: 'Product', technicalRequirements: ['Analytics', 'APIs', 'Agile Delivery'],
    interviewToken: 'pm-005-product-manager',
    openDate: '20/06/2026', closeDate: 'N/A',
    clicks: 51, completed: 3, live: true,
  },
];

export function getInterviewUrl(token: string) {
  return `${window.location.origin}/i/${token}`;
}

export async function copyToClipboard(text: string) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}
