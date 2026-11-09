import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Knowledge, KnowledgePage, KnowledgeQuery, KnowledgeWrite } from '../models/knowledge.model';

@Injectable({ providedIn: 'root' })
export class KnowledgeApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/knowledges';

  list(query: KnowledgeQuery): Observable<KnowledgePage> {
    let params = new HttpParams()
      .set('skip', query.skip)
      .set('limit', query.limit);
    if (query.knowledge_type) params = params.set('knowledge_type', query.knowledge_type);
    if (query.status) params = params.set('status', query.status);
    if (query.q) params = params.set('q', query.q);
    if (query.is_favorite !== undefined) params = params.set('is_favorite', query.is_favorite);
    if (query.tag_id) params = params.set('tag_id', query.tag_id);
    return this.http.get<KnowledgePage>(this.base, { params });
  }

  get(id: string): Observable<HttpResponse<Knowledge>> {
    return this.http.get<Knowledge>(this.resource(id), { observe: 'response' });
  }

  create(payload: KnowledgeWrite): Observable<HttpResponse<Knowledge>> {
    return this.http.post<Knowledge>(this.base, payload, { observe: 'response' });
  }

  update(id: string, payload: KnowledgeWrite, etag: string): Observable<HttpResponse<Knowledge>> {
    return this.http.patch<Knowledge>(this.resource(id), payload, {
      observe: 'response', headers: { 'If-Match': etag },
    });
  }

  delete(id: string, etag: string): Observable<void> {
    return this.http.delete<void>(this.resource(id), { headers: { 'If-Match': etag } });
  }

  private resource(id: string): string {
    // ID comes from the KMS, never arbitrary path segments.
    return this.base + '/' + encodeURIComponent(id);
  }
}
