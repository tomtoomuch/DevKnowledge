import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { KnowledgeApiService } from './knowledge-api.service';
import { Knowledge, KnowledgeWrite } from '../models/knowledge.model';

const payload: KnowledgeWrite = {
  knowledge_type: 'CODE_SNIPPET',
  title: 'Exemple',
  content: 'print("Hello")',
  description: null,
  language_code: 'fr',
  difficulty_level: null,
  status: 'DRAFT',
  is_favorite: false,
};
const record: Knowledge = {
  ...payload,
  knowledge_id: 'e627de24-880c-4a22-b18e-7884ee0396a3',
  revision: 1,
  created_at: '2026-11-09T16:00:00Z',
  updated_at: '2026-11-09T16:00:00Z',
  validated_at: null,
  created_by_user_id: null,
  deleted_at: null,
};

describe('KnowledgeApiService', () => {
  let api: KnowledgeApiService;
  let mock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), KnowledgeApiService],
    });
    api = TestBed.inject(KnowledgeApiService);
    mock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => mock.verify());

  it('transmits server pagination and type/status filters', () => {
    let total = -1;
    api.list({ skip: 20, limit: 20, knowledge_type: 'CODE_SNIPPET', status: 'DRAFT' })
      .subscribe((page) => total = page.total);
    const req = mock.expectOne((request) => request.url === '/api/v1/knowledges');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('skip')).toBe('20');
    expect(req.request.params.get('limit')).toBe('20');
    expect(req.request.params.get('knowledge_type')).toBe('CODE_SNIPPET');
    expect(req.request.params.get('status')).toBe('DRAFT');
    req.flush({ items: [record], total: 1, skip: 20, limit: 20 });
    expect(total).toBe(1);
  });

  it('sends text and favorite filters to KMS before pagination', () => {
    api.list({ skip: 20, limit: 20, q: 'Docker compose', is_favorite: true }).subscribe();
    const req = mock.expectOne((request) => request.url === '/api/v1/knowledges');
    expect(req.request.params.get('q')).toBe('Docker compose');
    expect(req.request.params.get('is_favorite')).toBe('true');
    expect(req.request.params.get('skip')).toBe('20');
    req.flush({ items: [], total: 0, skip: 20, limit: 20 });
  });

  it('does not set optional filters for unfiltered requests', () => {
    api.list({ skip: 0, limit: 20 }).subscribe();
    const req = mock.expectOne('/api/v1/knowledges?skip=0&limit=20');
    expect(req.request.params.has('q')).toBe(false);
    expect(req.request.params.has('is_favorite')).toBe(false);
    req.flush({ items: [], total: 0, skip: 0, limit: 20 });
  });

  it('reads ETag from individual GET response', () => {
    let etag: string | null = null;
    api.get(record.knowledge_id).subscribe((response) => etag = response.headers.get('ETag'));
    const req = mock.expectOne('/api/v1/knowledges/' + record.knowledge_id);
    expect(req.request.method).toBe('GET');
    req.flush(record, { headers: { ETag: '"1"' } });
    expect(etag).toBe('"1"');
  });

  it('creates using only public writable fields', () => {
    api.create(payload).subscribe();
    const req = mock.expectOne('/api/v1/knowledges');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    expect(req.request.body).not.toHaveProperty('revision');
    req.flush(record, { status: 201, statusText: 'Created' });
  });

  it('uses the revision precondition on PATCH without retrying', () => {
    api.update(record.knowledge_id, payload, '"1"').subscribe();
    const req = mock.expectOne('/api/v1/knowledges/' + record.knowledge_id);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.headers.get('If-Match')).toBe('"1"');
    req.flush({ ...record, revision: 2 }, { headers: { ETag: '"2"' } });
  });

  it('uses the revision precondition on DELETE', () => {
    api.delete(record.knowledge_id, '"2"').subscribe();
    const req = mock.expectOne('/api/v1/knowledges/' + record.knowledge_id);
    expect(req.request.method).toBe('DELETE');
    expect(req.request.headers.get('If-Match')).toBe('"2"');
    req.flush(null, { status: 204, statusText: 'No Content' });
  });
});
