import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TagApiService } from './tag-api.service';

describe('TagApiService', () => {
  let api: TagApiService;
  let http: HttpTestingController;
  const tag = { tag_id: 'e627de24-880c-4a22-b18e-7884ee0396a3', name: 'Docker' };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), TagApiService],
    });
    api = TestBed.inject(TagApiService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('lists tags using bounded server pagination', () => {
    let total = -1;
    api.list(5, 25).subscribe(page => total = page.total);
    const req = http.expectOne('/api/v1/tags?skip=5&limit=25');
    expect(req.request.method).toBe('GET');
    req.flush({ items: [tag], total: 8, skip: 5, limit: 25 });
    expect(total).toBe(8);
  });

  it('creates a tag without sending any server-owned identifier', () => {
    api.create('Docker').subscribe();
    const req = http.expectOne('/api/v1/tags');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Docker' });
    req.flush(tag, { status: 201, statusText: 'Created' });
  });

  it('retrieves a tag by UUID', () => {
    api.get(tag.tag_id).subscribe();
    const req = http.expectOne('/api/v1/tags/' + tag.tag_id);
    expect(req.request.method).toBe('GET');
    req.flush(tag);
  });
});
