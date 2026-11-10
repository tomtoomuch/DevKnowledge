import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type LocalRole = 'ADMIN' | 'EDITOR' | 'READER';
export type AccountStatus = 'ACTIVE' | 'DISABLED';

export interface ManagedUser {
  user_id: string;
  username: string;
  account_status: AccountStatus;
  roles: LocalRole[];
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
  last_login_at?: string | null;
}

export interface UserCreate {
  username: string;
  password: string;
  roles: LocalRole[];
}

export interface UserUpdate {
  username?: string;
  roles?: LocalRole[];
  account_status?: AccountStatus;
}

@Injectable({ providedIn: 'root' })
export class UserAdminService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/users';

  list(skip = 0, limit = 100): Observable<ManagedUser[]> {
    return this.http.get<ManagedUser[]>(this.base, {
      withCredentials: true, params: { skip, limit },
    });
  }

  create(payload: UserCreate): Observable<ManagedUser> {
    return this.http.post<ManagedUser>(this.base, payload, { withCredentials: true });
  }

  get(id: string): Observable<ManagedUser> {
    return this.http.get<ManagedUser>(this.path(id), { withCredentials: true });
  }

  update(id: string, revision: number, changes: UserUpdate): Observable<ManagedUser> {
    return this.http.patch<ManagedUser>(this.path(id), changes, {
      withCredentials: true, headers: { 'If-Match': '"' + revision + '"' },
    });
  }

  resetPassword(id: string, revision: number, password: string): Observable<void> {
    return this.http.post<void>(this.path(id) + '/password', { password }, {
      withCredentials: true, headers: { 'If-Match': '"' + revision + '"' },
    });
  }

  delete(id: string, revision: number): Observable<void> {
    return this.http.delete<void>(this.path(id), {
      withCredentials: true, headers: { 'If-Match': '"' + revision + '"' },
    });
  }

  private path(id: string): string {
    return this.base + '/' + encodeURIComponent(id);
  }
}
