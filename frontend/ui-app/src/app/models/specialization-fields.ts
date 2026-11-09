/** Typed fields exposed by the KMS specialization contract (MLD v0.2).
 * Each field is rendered by a single reactive-form editor; no separate Angular
 * application, form or duplicate business model is created.
 */
import { KnowledgeType } from './knowledge.model';

export type DetailKind = 'text' | 'multiline' | 'integer' | 'date' | 'datetime' | 'boolean' | 'uuid';
export interface DetailField {
  key: string;
  label: string;
  kind: DetailKind;
  required?: boolean;
  maxLength?: number;
  min?: number;
  max?: number;
}

const t = (key: string, label: string, maxLength?: number, required = false): DetailField => ({
  key, label, kind: 'text', maxLength, required,
});
const m = (key: string, label: string): DetailField => ({ key, label, kind: 'multiline' });
const b = (key: string, label: string): DetailField => ({ key, label, kind: 'boolean' });
const d = (key: string, label: string): DetailField => ({ key, label, kind: 'date' });
const dt = (key: string, label: string): DetailField => ({ key, label, kind: 'datetime' });
const uuid = (key: string, label: string): DetailField => ({ key, label, kind: 'uuid' });
const n = (key: string, label: string, min = 0, max?: number): DetailField => ({
  key, label, kind: 'integer', min, max,
});

export const SPECIALIZATION_FIELDS: Record<KnowledgeType, readonly DetailField[]> = {
  CODE_SNIPPET: [
    m('code', 'Code *'), t('programming_language', 'Langage de programmation *', 50, true),
    t('framework', 'Framework', 100), t('snippet_version', 'Version', 30),
    t('entry_point', 'Point d’entrée', 255), m('input_example', 'Exemple d’entrée'),
    m('output_example', 'Exemple de sortie'), m('execution_context', 'Contexte d’exécution'),
    b('is_executable', 'Exécutable'), t('license', 'Licence', 100),
  ],
  TERMINAL_COMMAND: [
    m('command', 'Commande *'), t('shell', 'Shell *', 50, true),
    t('operating_system', 'Système d’exploitation', 100),
    t('working_directory', 'Dossier de travail', 500), m('parameters', 'Paramètres'),
    m('expected_output', 'Résultat attendu'), t('risk_level', 'Niveau de risque', 30),
    b('requires_sudo', 'Privilèges administrateur requis'),
    b('is_destructive', 'Commande destructive'), m('execution_notes', 'Notes d’exécution'),
  ],
  TECHNICAL_PROCEDURE: [
    m('objective', 'Objectif'), m('environment', 'Environnement'),
    n('estimated_duration_minutes', 'Durée estimée (minutes)'),
    t('difficulty', 'Difficulté', 30), m('rollback_procedure', 'Procédure de retour arrière'),
    m('validation_criteria', 'Critères de validation'),
  ],
  COURSE_NOTE: [
    uuid('module_id', 'Identifiant du module (UUID)'),
    t('concept', 'Concept', 255), m('definition', 'Définition'),
    m('explanation', 'Explication'), n('mastery_level', 'Niveau de maîtrise', 0, 32767),
  ],
  BUG_FIX: [
    t('error_title', 'Titre de l’erreur', 255), m('error_message', 'Message d’erreur'),
    t('error_code', 'Code d’erreur', 100), m('symptoms', 'Symptômes'),
    m('root_cause', 'Cause racine'), m('solution', 'Solution'),
    m('code_before', 'Code avant'), m('code_after', 'Code après'),
    m('environment', 'Environnement'), t('resolution_status', 'Statut de résolution', 30),
    dt('verified_at', 'Date de vérification'),
  ],
  DOCUMENTATION_RESOURCE: [
    t('url', 'URL'), t('resource_type', 'Type de ressource', 50),
    t('publisher', 'Éditeur', 150), d('publication_date', 'Date de publication'),
    dt('accessed_at', 'Date de consultation'),
    t('version_reference', 'Version de référence', 50),
    m('summary', 'Résumé'), t('reliability_level', 'Fiabilité', 30),
    b('is_official', 'Source officielle'),
  ],
  BEST_PRACTICE: [
    m('principle', 'Principe'), m('rationale', 'Justification'),
    m('recommendation', 'Recommandation'), m('anti_pattern', 'Anti-pattern'),
    m('benefits', 'Bénéfices'), m('application_context', 'Contexte d’application'),
    uuid('reference_standard_id', 'Norme de référence (UUID)'),
    m('validation_criteria', 'Critères de validation'),
  ],
  COMPLIANCE_STANDARD: [
    t('reference_code', 'Code de référence *', 100, true),
    t('compliance_type', 'Type de conformité', 50),
    t('issuing_organization', 'Organisme émetteur', 150),
    t('jurisdiction', 'Juridiction', 100), m('scope', 'Périmètre'),
    m('applicability', 'Applicabilité'), t('official_url', 'URL officielle'),
  ],
};

// Large code and command text areas are required by the KMS and must not be
// silently truncated to a short input field.
for (const key of ['code', 'command']) {
  const type = key === 'code' ? 'CODE_SNIPPET' : 'TERMINAL_COMMAND';
  const item = SPECIALIZATION_FIELDS[type].find(field => field.key === key);
  if (item) item.required = true;
}
export type DetailValue = string | number | boolean | null;
export type KnowledgeDetails = Record<string, DetailValue>;
/** Serialize only populated properties. A false boolean is not an empty value. */
export function toSpecialization(
  fields: readonly DetailField[], values: Record<string, string>,
): KnowledgeDetails {
  const result: KnowledgeDetails = {};
  for (const field of fields) {
    const raw = (values[field.key] ?? '').trim();
    if (raw === '') continue;
    switch (field.kind) {
      case 'boolean':
        result[field.key] = raw === 'true';
        break;
      case 'integer':
        if (!/^-?\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
          throw new Error('Entier invalide : ' + field.label);
        }
        result[field.key] = Number(raw);
        break;
      case 'datetime': {
        const date = new Date(raw);
        if (!Number.isFinite(date.getTime())) throw new Error('Date invalide : ' + field.label);
        result[field.key] = date.toISOString();
        break;
      }
      default:
        result[field.key] = raw;
    }
  }
  return result;
}

export function detailToFormValue(field: DetailField, details: KnowledgeDetails | null | undefined): string {
  const value = details?.[field.key];
  if (value === undefined || value === null) return '';
  if (field.kind === 'boolean') return String(value);
  if (field.kind === 'datetime') {
    const date = new Date(String(value));
    if (!Number.isFinite(date.getTime())) return '';
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }
  return String(value);
}

export function displayDetailValue(field: DetailField, value: DetailValue): string {
  if (field.kind === 'boolean') return value === true ? 'Oui' : 'Non';
  if (field.kind === 'datetime') {
    const date = new Date(String(value));
    return Number.isFinite(date.getTime()) ? date.toLocaleString('fr-FR') : String(value);
  }
  return String(value);
}
