import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  RelationPage, RelationType, KnowledgeRelation, KnowledgeRelationWrite,
} from '../models/relations.model';

@Injectable({ providedIn: 'root' })
export class RelationsApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/knowledge-relations';

  types(): Observable<RelationType[]> {
    return this.http.get<RelationType[]>('/api/v1/relation-types');
  }

  list(knowledgeId: string, skip = 0, limit = 20): Observable<RelationPage> {
    const params = new HttpParams().set('knowledge_id', knowledgeId)
      .set('skip', skip).set('limit', limit);
    return this.http.get<RelationPage>(this.base, { params });
  }

  get(relationId: string): Observable<HttpResponse<KnowledgeRelation>> {
    return this.http.get<KnowledgeRelation>(this.resource(relationId), { observe: 'response' });
  }

  create(payload: KnowledgeRelationWrite): Observable<HttpResponse<KnowledgeRelation>> {
    return this.http.post<KnowledgeRelation>(this.base, payload, { observe: 'response' });
  }

  updateNotes(
    relationId: string, notes: string | null, revision: number,
  ): Observable<HttpResponse<KnowledgeRelation>> {
    return this.http.patch<KnowledgeRelation>(this.resource(relationId), {
      relation_notes: notes,
    }, { headers: { 'If-Match': '"' + revision + '"' }, observe: 'response' });
  }

  delete(relationId: string, revision: number): Observable<void> {
    return this.http.delete<void>(this.resource(relationId), {
      headers: { 'If-Match': '"' + revision + '"' },
    });
  }

  private resource(id: string): string {
    return this.base + '/' + encodeURIComponent(id);
  }
}
