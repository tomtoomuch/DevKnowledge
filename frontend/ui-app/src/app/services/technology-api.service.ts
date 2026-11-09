import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CatalogPage, TechnologyRecord, TechnologyVersionRecord } from '../models/technology.model';

@Injectable({ providedIn: 'root' })
export class TechnologyApiService {
  private readonly http = inject(HttpClient);
  private readonly techBase = '/api/v1/technologies';
  private readonly versionBase = '/api/v1/technology-versions';

  listTechnologies(skip = 0, limit = 100): Observable<CatalogPage<TechnologyRecord>> {
    return this.http.get<CatalogPage<TechnologyRecord>>(this.techBase, {
      params: new HttpParams().set('skip', skip).set('limit', limit),
    });
  }

  createTechnology(name: string, category: string | null): Observable<TechnologyRecord> {
    return this.http.post<TechnologyRecord>(this.techBase, { name, category });
  }

  getTechnology(id: string): Observable<TechnologyRecord> {
    return this.http.get<TechnologyRecord>(this.techBase + '/' + encodeURIComponent(id));
  }

  listVersions(
    skip = 0, limit = 100, technologyId?: string,
  ): Observable<CatalogPage<TechnologyVersionRecord>> {
    let params = new HttpParams().set('skip', skip).set('limit', limit);
    if (technologyId) params = params.set('technology_id', technologyId);
    return this.http.get<CatalogPage<TechnologyVersionRecord>>(this.versionBase, { params });
  }

  createVersion(
    technologyId: string, version: string, releaseDate: string | null,
  ): Observable<TechnologyVersionRecord> {
    return this.http.post<TechnologyVersionRecord>(this.versionBase, {
      technology_id: technologyId, version, release_date: releaseDate,
    });
  }

  getVersion(id: string): Observable<TechnologyVersionRecord> {
    return this.http.get<TechnologyVersionRecord>(
      this.versionBase + '/' + encodeURIComponent(id),
    );
  }
}
