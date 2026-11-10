import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { AccountStatus, LocalRole, ManagedUser, UserAdminService } from '../services/user-admin.service';

const USERNAME_PATTERN = /^[a-zA-Z0-9_.-]{3,40}$/;

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
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  readonly users = signal<ManagedUser[]>([]);
  readonly page = signal(0);
  readonly selected = signal<ManagedUser | null>(null);
  readonly currentId = signal<string | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly confirmingDelete = signal(false);
  readonly roles: { code: LocalRole; label: string }[] = [
    { code: 'READER', label: 'Lecteur — consultation' },
    { code: 'EDITOR', label: 'Éditeur — lecture, création, modification' },
    { code: 'ADMIN', label: 'Administrateur — tous les droits et comptes' },
  ];

  readonly form = new FormGroup({
    username: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.pattern(USERNAME_PATTERN)],
    }),
    role: new FormControl<LocalRole>('READER', { nonNullable: true }),
    password: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.minLength(12), Validators.maxLength(256)],
    }),
    confirmation: new FormControl('', {
      nonNullable: true, validators: [Validators.required],
    }),
  });

  readonly editForm = new FormGroup({
    username: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.pattern(USERNAME_PATTERN)],
    }),
    account_status: new FormControl<AccountStatus>('ACTIVE', { nonNullable: true }),
    admin: new FormControl(false, { nonNullable: true }),
    editor: new FormControl(false, { nonNullable: true }),
    reader: new FormControl(false, { nonNullable: true }),
  });

  readonly passwordForm = new FormGroup({
    password: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.minLength(12), Validators.maxLength(256)],
    }),
    confirmation: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  ngOnInit(): void {
    this.auth.me().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: identity => this.currentId.set(identity.user_id),
    });
    this.refresh();
  }

  refresh(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set('');
    this.api.list(this.page() * 100, 100).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false)),
    ).subscribe({
      next: users => this.users.set(users),
      error: (error: unknown) => this.error.set(this.message(error)),
    });
  }

  nextPage(): void {
    if (this.users().length !== 100) return;
    this.page.update(value => value + 1);
    this.refresh();
  }

  previousPage(): void {
    if (this.page() === 0) return;
    this.page.update(value => value - 1);
    this.refresh();
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
    if (password !== confirmation || !password.trim()) {
      this.error.set('Les mots de passe doivent correspondre et contenir des caractères non blancs.');
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
          this.page.set(0);
          this.refresh();
        },
        error: (error: unknown) => this.error.set(this.message(error)),
      });
  }

  inspect(user: ManagedUser): void {
    if (this.saving()) return;
    this.confirmingDelete.set(false);
    this.error.set('');
    this.notice.set('');
    this.api.get(user.user_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: fresh => this.showUser(fresh),
      error: (error: unknown) => this.error.set(this.message(error)),
    });
  }

  private showUser(user: ManagedUser): void {
    this.selected.set(user);
    this.editForm.setValue({
      username: user.username, account_status: user.account_status,
      admin: user.roles.includes('ADMIN'),
      editor: user.roles.includes('EDITOR'),
      reader: user.roles.includes('READER'),
    });
    this.editForm.markAsPristine();
    this.passwordForm.reset({ password: '', confirmation: '' });
  }

  closeDetails(): void {
    this.selected.set(null);
    this.confirmingDelete.set(false);
    this.passwordForm.reset({ password: '', confirmation: '' });
    this.error.set('');
  }

  private selectedRoles(): LocalRole[] {
    const form = this.editForm.getRawValue();
    return [
      ...(form.admin ? ['ADMIN' as LocalRole] : []),
      ...(form.editor ? ['EDITOR' as LocalRole] : []),
      ...(form.reader ? ['READER' as LocalRole] : []),
    ];
  }

  saveUser(): void {
    const user = this.selected();
    if (!user || this.saving() || this.editForm.invalid) return;
    const roles = this.selectedRoles();
    if (!roles.length) {
      this.error.set('Sélectionne au moins un rôle.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.api.update(user.user_id, user.revision, {
      username: this.editForm.controls.username.value,
      account_status: this.editForm.controls.account_status.value,
      roles,
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)))
      .subscribe({
        next: updated => {
          this.showUser(updated);
          this.notice.set('Compte modifié. Les anciennes sessions sont révoquées.');
          this.refresh();
        },
        error: (error: unknown) => this.error.set(this.message(error)),
      });
  }

  rotatePassword(): void {
    const user = this.selected();
    if (!user || this.saving() || this.passwordForm.invalid) return;
    const { password, confirmation } = this.passwordForm.getRawValue();
    if (!password.trim() || password !== confirmation) {
      this.error.set('Les nouveaux mots de passe sont invalides ou différents.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.passwordForm.reset({ password: '', confirmation: '' });
    this.api.resetPassword(user.user_id, user.revision, password)
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.notice.set('Mot de passe réinitialisé. Toutes les sessions précédentes sont révoquées.');
          this.inspect(user);
          this.refresh();
        },
        error: (error: unknown) => this.error.set(this.message(error)),
      });
  }

  deleteUser(): void {
    const user = this.selected();
    if (!user || !this.confirmingDelete() || this.saving() || user.user_id === this.currentId()) return;
    this.saving.set(true);
    this.error.set('');
    this.api.delete(user.user_id, user.revision)
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.closeDetails();
          this.notice.set('Compte supprimé logiquement et sessions révoquées.');
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
      case 404: return 'Compte introuvable (il a peut-être été supprimé).';
      case 409: return 'Conflit : identifiant déjà utilisé ou protection du dernier administrateur / de ton propre compte.';
      case 412: return 'Ce compte a été modifié entre-temps. Actualise sa fiche avant de réessayer.';
      case 422: return 'Les champs sont invalides (identifiant, rôle, statut ou mot de passe).';
      case 428: return 'Une révision de compte est requise.';
      default: return 'Opération impossible (HTTP ' + error.status + ').';
    }
  }
}
