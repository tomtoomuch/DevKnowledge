import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface LocalIdentity {
  user_id: string;
  username: string;
  roles: string[];
  permissions: string[];
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/auth';

  me(): Observable<LocalIdentity> {
    return this.http.get<LocalIdentity>(this.base + '/me', { withCredentials: true });
  }

  login(username: string, password: string): Observable<LocalIdentity> {
    return this.http.post<LocalIdentity>(
      this.base + '/login', { username, password }, { withCredentials: true },
    );
  }

  logout(): Observable<void> {
    return this.http.post<void>(this.base + '/logout', {}, { withCredentials: true });
  }
}
