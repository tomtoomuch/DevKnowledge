import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let api: AuthService;
  let mock: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), AuthService],
    });
    api = TestBed.inject(AuthService);
    mock = TestBed.inject(HttpTestingController);
  });
  afterEach(() => mock.verify());

  it('reads the active local session', () => {
    api.me().subscribe(p => expect(p.permissions).toContain('knowledge.read'));
    const req = mock.expectOne('/api/v1/auth/me');
    expect(req.request.withCredentials).toBe(true);
    req.flush({ user_id: 'id', username: 'reader', roles: ['READER'], permissions: ['knowledge.read'] });
  });

  it('posts login credentials without storing them on the client', () => {
    api.login('admin', 'top secret').subscribe();
    const req = mock.expectOne('/api/v1/auth/login');
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.body).toEqual({ username: 'admin', password: 'top secret' });
    req.flush({ user_id: 'id', username: 'admin', roles: ['ADMIN'], permissions: ['knowledge.read'] });
  });

  it('revokes via the session endpoint', () => {
    api.logout().subscribe();
    const req = mock.expectOne('/api/v1/auth/logout');
    expect(req.request.method).toBe('POST');
    expect(req.request.withCredentials).toBe(true);
    req.flush(null, { status: 204, statusText: 'No Content' });
  });
});
