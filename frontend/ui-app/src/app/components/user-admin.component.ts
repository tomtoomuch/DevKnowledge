import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { LocalRole, ManagedUser, UserAdminService } from '../services/user-admin.service';

@Component({
  selector: 'app-user-admin',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './user-admin.component.html',
  styleUrl: './user-admin.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UserAdminComponent implements OnInit {
  private readonly api = inject(UserAdminService);
  private readonly destroyRef = inject(DestroyRef);
  readonly users = signal<ManagedUser[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly roles: { code: LocalRole; label: string }[] = [
    { code: 'READER', label: 'Lecteur — consultation' },
    { code: 'EDITOR', label: 'Éditeur — lecture, création, modification' },
    { code: 'ADMIN', label: 'Administrateur — tous les droits et comptes' },
  ];

  readonly form = new FormGroup({
    username: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.pattern(/^[a-zA-Z0-9_.-]{3,40}$/)],
    }),
    role: new FormControl<LocalRole>('READER', { nonNullable: true }),
    password: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.minLength(12), Validators.maxLength(256)],
    }),
    confirmation: new FormControl('', {
      nonNullable: true, validators: [Validators.required],
    }),
  });

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set('');
    this.api.list().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: users => this.users.set(users),
      error: (error: unknown) => this.error.set(this.message(error)),
    });
  }

  submit(): void {
    if (this.saving()) return;
    this.notice.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Identifiant invalide ou mot de passe trop court (12 caractères minimum).');
      return;
    }
    const { username, role, password, confirmation } = this.form.getRawValue();
    if (password !== confirmation) {
      this.error.set('Les deux mots de passe ne correspondent pas.');
      return;
    }
    if (!password.trim()) {
      this.error.set('Le mot de passe ne peut pas contenir uniquement des espaces.');
      return;
    }
    this.error.set('');
    this.saving.set(true);
    // Never persist credentials in localStorage or logs.
    this.form.controls.password.reset();
    this.form.controls.confirmation.reset();
    this.api.create({ username: username.trim(), password, roles: [role] })
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)))
      .subscribe({
        next: user => {
          this.notice.set('Compte ' + user.username + ' créé.');
          this.form.controls.username.reset();
          this.form.controls.role.setValue('READER');
          this.form.markAsPristine();
          this.refresh();
        },
        error: (error: unknown) => this.error.set(this.message(error)),
      });
  }

  private message(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) return 'Erreur inattendue.';
    switch (error.status) {
      case 0: return 'Gateway inaccessible.';
      case 401: return 'Session expirée : reconnecte-toi.';
      case 403: return 'Droits administrateur requis.';
      case 409: return 'Cet identifiant existe déjà.';
      case 422: return 'Identifiant ou mot de passe refusé par le service.';
      default: return 'Opération impossible (HTTP ' + error.status + ').';
    }
  }
}
