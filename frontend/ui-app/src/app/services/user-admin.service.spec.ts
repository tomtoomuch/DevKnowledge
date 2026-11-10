import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { UserAdminService } from './user-admin.service';

describe('UserAdminService', () => {
  let service: UserAdminService;
  let mock: HttpTestingController;
  const id = 'a607237e-9050-4992-88b5-34c36b46d044';
  const user = {
    user_id: id, username: 'reader', account_status: 'ACTIVE',
    roles: ['READER'], revision: 1,
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), UserAdminService],
    });
    service = TestBed.inject(UserAdminService);
    mock = TestBed.inject(HttpTestingController);
  });
  afterEach(() => mock.verify());

  it('lists sanitized profiles using server pagination', () => {
    service.list(100, 20).subscribe(users => {
      expect(users[0].roles).toEqual(['READER']);
      expect(users[0]).not.toHaveProperty('password_hash');
    });
    const req = mock.expectOne(r => r.url === '/api/v1/users');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('skip')).toBe('100');
    expect(req.request.params.get('limit')).toBe('20');
    expect(req.request.withCredentials).toBe(true);
    req.flush([user]);
  });

  it('creates a user without server-owned fields', () => {
    service.create({username: 'reader', password: 'safe-passphrase-2026', roles: ['READER']}).subscribe();
    const req = mock.expectOne('/api/v1/users');
    expect(req.request.method).toBe('POST');
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.body).toEqual({
      username: 'reader', password: 'safe-passphrase-2026', roles: ['READER'],
    });
    req.flush(user, {status: 201, statusText: 'Created'});
  });

  it('reads a single user without credentials in the response', () => {
    service.get(id).subscribe(result => expect(result).not.toHaveProperty('password_hash'));
    const req = mock.expectOne('/api/v1/users/' + id);
    expect(req.request.method).toBe('GET');
    req.flush(user);
  });

  it('enforces ETag for role/status updates', () => {
    service.update(id, 7, {username: 'updated', account_status: 'DISABLED',
      roles: ['EDITOR']}).subscribe();
    const req = mock.expectOne('/api/v1/users/' + id);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.headers.get('If-Match')).toBe('"7"');
    expect(req.request.body).toEqual({username:'updated',account_status:'DISABLED',roles:['EDITOR']});
    req.flush({...user, revision: 8, roles:['EDITOR'], account_status:'DISABLED'});
  });

  it('resets password and soft-deletes with independent revision checks', () => {
    service.resetPassword(id, 3, 'safe-new-passphrase-2026').subscribe();
    const reset = mock.expectOne('/api/v1/users/' + id + '/password');
    expect(reset.request.method).toBe('POST');
    expect(reset.request.body).toEqual({ password: 'safe-new-passphrase-2026' });
    expect(reset.request.headers.get('If-Match')).toBe('"3"');
    reset.flush(null, { status: 204, statusText: 'No Content' });
    service.delete(id, 4).subscribe();
    const del = mock.expectOne('/api/v1/users/' + id);
    expect(del.request.method).toBe('DELETE');
    expect(del.request.headers.get('If-Match')).toBe('"4"');
    del.flush(null, { status: 204, statusText: 'No Content' });
  });
});
