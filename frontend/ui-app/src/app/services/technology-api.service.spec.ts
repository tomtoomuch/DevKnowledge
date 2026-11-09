import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TechnologyApiService } from './technology-api.service';

describe('TechnologyApiService', () => {
  let api: TechnologyApiService;
  let http: HttpTestingController;
  const tech = { technology_id: 'e627de24-880c-4a22-b18e-7884ee0396a3', name: 'Python', category: 'Language' };
  const version = {
    technology_version_id: 'a607237e-9050-4992-88b5-34c36b46d044',
    technology_id: tech.technology_id, version: '3.14', release_date: '2026-10-01',
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), TechnologyApiService],
    });
    api = TestBed.inject(TechnologyApiService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('lists technologies with server pagination', () => {
    api.listTechnologies(5, 25).subscribe();
    const req = http.expectOne('/api/v1/technologies?skip=5&limit=25');
    expect(req.request.method).toBe('GET');
    req.flush({ items: [tech], total: 1, skip: 5, limit: 25 });
  });

  it('creates a reusable technology and retrieves its UUID', () => {
    api.createTechnology('Python', 'Language').subscribe();
    const req = http.expectOne('/api/v1/technologies');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ name: 'Python', category: 'Language' });
    req.flush(tech, { status: 201, statusText: 'Created' });
    api.getTechnology(tech.technology_id).subscribe();
    const get = http.expectOne('/api/v1/technologies/' + tech.technology_id);
    get.flush(tech);
  });

  it('lists versions by parent technology and creates dated version', () => {
    api.listVersions(0, 20, tech.technology_id).subscribe();
    const req = http.expectOne((request) => request.url === '/api/v1/technology-versions');
    expect(req.request.params.get('technology_id')).toBe(tech.technology_id);
    req.flush({ items: [version], total: 1, skip: 0, limit: 20 });
    api.createVersion(tech.technology_id, '3.14', '2026-10-01').subscribe();
    const post = http.expectOne('/api/v1/technology-versions');
    expect(post.request.body).toEqual({
      technology_id: tech.technology_id, version: '3.14', release_date: '2026-10-01',
    });
    post.flush(version, { status: 201, statusText: 'Created' });
    api.getVersion(version.technology_version_id).subscribe();
    const get = http.expectOne('/api/v1/technology-versions/' + version.technology_version_id);
    get.flush(version);
  });
});
