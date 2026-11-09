import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { beforeEach, afterEach, describe, expect, it } from 'vitest';
import { UserAdminService } from './user-admin.service';

describe('UserAdminService', () => {
  let service: UserAdminService;
  let mock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), UserAdminService],
    });
    service = TestBed.inject(UserAdminService);
    mock = TestBed.inject(HttpTestingController);
  });
  afterEach(() => mock.verify());

  it('reads public local profiles', () => {
    service.list().subscribe(users => {
      expect(users[0].roles).toEqual(['ADMIN']);
      expect(users[0]).not.toHaveProperty('password_hash');
    });
    const req = mock.expectOne('/api/v1/users');
    expect(req.request.method).toBe('GET');
    expect(req.request.withCredentials).toBe(true);
    req.flush([{user_id: 'id', username: 'admin', account_status: 'ACTIVE', roles: ['ADMIN']}]);
  });

  it('sends an explicit role and credential only to the create endpoint', () => {
    service.create({username: 'reader', password: 'safe-passphrase-2026', roles: ['READER']}).subscribe();
    const req = mock.expectOne('/api/v1/users');
    expect(req.request.method).toBe('POST');
    expect(req.request.withCredentials).toBe(true);
    expect(req.request.body).toEqual({
      username: 'reader', password: 'safe-passphrase-2026', roles: ['READER'],
    });
    req.flush({user_id: 'new-id', username: 'reader', roles: ['READER'], account_status: 'ACTIVE'},
      {status: 201, statusText: 'Created'});
  });
});
