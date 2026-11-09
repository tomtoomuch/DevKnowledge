import { describe, expect, it } from 'vitest';
import { SPECIALIZATION_FIELDS, detailToFormValue, toSpecialization } from './specialization-fields';
import { KNOWLEDGE_TYPES } from './knowledge.model';

describe('specialization metadata and serialization', () => {
  it('describes all eight types and all required MLD fields', () => {
    expect(Object.keys(SPECIALIZATION_FIELDS)).toHaveLength(8);
    expect(KNOWLEDGE_TYPES.map(type => type.code)).toEqual(Object.keys(SPECIALIZATION_FIELDS));
    expect(SPECIALIZATION_FIELDS.CODE_SNIPPET.filter(f => f.required).map(f => f.key))
      .toEqual(['code', 'programming_language']);
    expect(SPECIALIZATION_FIELDS.TERMINAL_COMMAND.filter(f => f.required).map(f => f.key))
      .toEqual(['command', 'shell']);
    expect(SPECIALIZATION_FIELDS.COMPLIANCE_STANDARD.filter(f => f.required).map(f => f.key))
      .toEqual(['reference_code']);
  });

  it('serializes booleans including false, integers and ISO timestamps', () => {
    const command = toSpecialization(SPECIALIZATION_FIELDS.TERMINAL_COMMAND, {
      command: '  git status  ', shell: ' bash ', is_destructive: 'false',
      requires_sudo: 'true', risk_level: '',
    });
    expect(command).toEqual({
      command: 'git status', shell: 'bash', is_destructive: false, requires_sudo: true,
    });
    expect(toSpecialization(SPECIALIZATION_FIELDS.TECHNICAL_PROCEDURE, {
      estimated_duration_minutes: '15', objective: 'Importer',
    })).toEqual({ estimated_duration_minutes: 15, objective: 'Importer' });
    const verified = toSpecialization(SPECIALIZATION_FIELDS.BUG_FIX, {
      verified_at: '2026-11-09T14:30',
    });
    expect(verified.verified_at).toBe(new Date('2026-11-09T14:30').toISOString());
  });

  it('omits optional blank fields without misinterpreting boolean false', () => {
    expect(toSpecialization(SPECIALIZATION_FIELDS.DOCUMENTATION_RESOURCE, {
      url: 'https://example.test/', is_official: '', publication_date: '',
    })).toEqual({ url: 'https://example.test/' });
  });

  it('rejects decimal and unsafe numbers instead of silently rounding', () => {
    for (const raw of ['2.5', '1e3', '9007199254740992']) {
      expect(() => toSpecialization(SPECIALIZATION_FIELDS.COURSE_NOTE, {
        mastery_level: raw,
      })).toThrow();
    }
  });

  it('round-trips boolean and UTC timestamp form values', () => {
    const booleanField = SPECIALIZATION_FIELDS.DOCUMENTATION_RESOURCE.find(f => f.key === 'is_official')!;
    expect(detailToFormValue(booleanField, { is_official: false })).toBe('false');
    const dateField = SPECIALIZATION_FIELDS.BUG_FIX.find(f => f.key === 'verified_at')!;
    const original = '2026-11-09T14:30:00.000Z';
    const input = detailToFormValue(dateField, { verified_at: original });
    expect(toSpecialization([dateField], { verified_at: input }).verified_at).toBe(original);
  });
});
