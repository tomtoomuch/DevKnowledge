/** Public KMS knowledge contract: generic data plus typed specialization. */
import type { KnowledgeDetails } from './specialization-fields';
export const KNOWLEDGE_TYPES = [
  { code: 'CODE_SNIPPET', label: 'Extrait de code', icon: '⌘' },
  { code: 'TERMINAL_COMMAND', label: 'Commande terminal', icon: '>_' },
  { code: 'TECHNICAL_PROCEDURE', label: 'Procédure technique', icon: '☷' },
  { code: 'COURSE_NOTE', label: 'Note de cours', icon: '▤' },
  { code: 'BUG_FIX', label: 'Correction de bug', icon: '✦' },
  { code: 'DOCUMENTATION_RESOURCE', label: 'Ressource documentaire', icon: '↗' },
  { code: 'BEST_PRACTICE', label: 'Bonne pratique', icon: '✓' },
  { code: 'COMPLIANCE_STANDARD', label: 'Norme et conformité', icon: '◇' },
] as const;

export type KnowledgeType = (typeof KNOWLEDGE_TYPES)[number]['code'];
export type KnowledgeStatus = 'DRAFT' | 'VALIDATED' | 'ARCHIVED';

export interface KnowledgeWrite {
  knowledge_type: KnowledgeType;
  title: string;
  content: string;
  description: string | null;
  language_code: string | null;
  difficulty_level: string | null;
  status: string;
  is_favorite: boolean;
  /** Optional for historical generic knowledge; filled for specialized records. */
  details?: KnowledgeDetails | null;
}

export interface Knowledge extends KnowledgeWrite {
  knowledge_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
  validated_at: string | null;
  created_by_user_id: string | null;
  deleted_at: string | null;
}

export interface KnowledgePage {
  items: Knowledge[];
  total: number;
  skip: number;
  limit: number;
}

export interface KnowledgeQuery {
  skip: number;
  limit: number;
  knowledge_type?: KnowledgeType;
  status?: string;
  q?: string;
  is_favorite?: boolean;
}

export function knowledgeTypeLabel(code: string): string {
  return KNOWLEDGE_TYPES.find((item) => item.code === code)?.label ?? code;
}
