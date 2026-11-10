import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { RelationsApiService } from './relations-api.service';

describe('RelationsApiService', () => {
  let api: RelationsApiService;
  let http: HttpTestingController;
  const uuid = 'e627de24-880c-4a22-b18e-7884ee0396a3';
  const target = 'a607237e-9050-4992-88b5-34c36b46d044';

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), RelationsApiService],
    });
    api = TestBed.inject(RelationsApiService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('reads types and relations scoped to a knowledge before pagination', () => {
    api.types().subscribe();
    http.expectOne('/api/v1/relation-types').flush([]);
    api.list(uuid, 20, 10).subscribe();
    const req = http.expectOne(r => r.url === '/api/v1/knowledge-relations');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('knowledge_id')).toBe(uuid);
    expect(req.request.params.get('skip')).toBe('20');
    expect(req.request.params.get('limit')).toBe('10');
    req.flush({ items: [], total: 0, skip: 20, limit: 10 });
  });

  it('creates a relation using server-owned ID/revision only', () => {
    api.create({
      origin_knowledge_id: uuid, target_knowledge_id: target,
      relation_type_id: uuid, relation_notes: 'Prérequis',
    }).subscribe();
    const req = http.expectOne('/api/v1/knowledge-relations');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).not.toHaveProperty('revision');
    expect(req.request.body).not.toHaveProperty('relation_id');
    req.flush({ relation_id: target }, { status: 201, statusText: 'Created' });
  });

  it('preserves If-Match on PATCH and DELETE without auto-retry', () => {
    api.get(uuid).subscribe();
    http.expectOne('/api/v1/knowledge-relations/' + uuid).flush({});
    api.updateNotes(uuid, null, 7).subscribe();
    const patch = http.expectOne('/api/v1/knowledge-relations/' + uuid);
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.headers.get('If-Match')).toBe('"7"');
    expect(patch.request.body).toEqual({ relation_notes: null });
    patch.flush({});
    api.delete(uuid, 8).subscribe();
    const del = http.expectOne('/api/v1/knowledge-relations/' + uuid);
    expect(del.request.method).toBe('DELETE');
    expect(del.request.headers.get('If-Match')).toBe('"8"');
    del.flush(null, { status: 204, statusText: 'No Content' });
  });
});
