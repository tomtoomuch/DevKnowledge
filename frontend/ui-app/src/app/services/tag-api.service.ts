import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { TagPage, TagRecord } from '../models/tag.model';

@Injectable({ providedIn: 'root' })
export class TagApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/tags';

  list(skip = 0, limit = 100): Observable<TagPage> {
    return this.http.get<TagPage>(this.base, {
      params: new HttpParams().set('skip', skip).set('limit', limit),
    });
  }

  create(name: string): Observable<TagRecord> {
    return this.http.post<TagRecord>(this.base, { name });
  }

  get(id: string): Observable<TagRecord> {
    return this.http.get<TagRecord>(this.base + '/' + encodeURIComponent(id));
  }
}
