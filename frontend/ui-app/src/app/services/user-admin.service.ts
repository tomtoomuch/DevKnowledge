import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type LocalRole = 'ADMIN' | 'EDITOR' | 'READER';

export interface ManagedUser {
  user_id: string;
  username: string;
  account_status: string;
  roles: LocalRole[];
}

export interface UserCreate {
  username: string;
  password: string;
  roles: LocalRole[];
}

@Injectable({ providedIn: 'root' })
export class UserAdminService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/users';

  list(): Observable<ManagedUser[]> {
    return this.http.get<ManagedUser[]>(this.base, { withCredentials: true });
  }

  create(payload: UserCreate): Observable<ManagedUser> {
    return this.http.post<ManagedUser>(this.base, payload, { withCredentials: true });
  }
}
