import { CommonModule } from '@angular/common';
import { HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, finalize } from 'rxjs';
import {
  Knowledge, KnowledgeType, KnowledgeWrite, KNOWLEDGE_TYPES, knowledgeTypeLabel,
} from './models/knowledge.model';
import { KnowledgeApiService } from './services/knowledge-api.service';
import { AuthService, LocalIdentity } from './services/auth.service';

type EditorMode = 'view' | 'create' | 'edit';
const PAGE_SIZE = 20;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  private readonly api = inject(KnowledgeApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly authMode = signal<'checking' | 'login' | 'active'>('checking');
  readonly principal = signal<LocalIdentity | null>(null);
  readonly loginError = signal('');
  readonly loggingIn = signal(false);
  readonly loginForm = new FormGroup({
    username: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  readonly types = KNOWLEDGE_TYPES;
  readonly pageSize = PAGE_SIZE;
  readonly mode = signal<EditorMode>('view');
  readonly items = signal<Knowledge[]>([]);
  readonly selected = signal<Knowledge | null>(null);
  readonly etag = signal<string | null>(null);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly busy = signal(false);
  readonly detailLoading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly formError = signal('');
  readonly notice = signal('');
  readonly confirmingDelete = signal(false);
  readonly searchTerm = signal('');
  readonly favoritesOnly = signal(false);

  // The KMS now performs all list filters before pagination.
  readonly visibleItems = computed(() => this.items());
  private listSequence = 0;
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  readonly currentPage = computed(() => this.pageIndex() + 1);

  readonly search = new FormControl('', { nonNullable: true });
  readonly typeFilter = new FormControl<KnowledgeType | ''>('', { nonNullable: true });
  readonly statusFilter = new FormControl('', { nonNullable: true });
  readonly favoritesFilter = new FormControl(false, { nonNullable: true });

  readonly editor = new FormGroup({
    knowledge_type: new FormControl<KnowledgeType>('CODE_SNIPPET', {
      nonNullable: true, validators: [Validators.required],
    }),
    title: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.maxLength(150), Validators.pattern(/.*\S.*/s)],
    }),
    content: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.pattern(/[\s\S]*\S[\s\S]*/)],
    }),
    description: new FormControl('', { nonNullable: true }),
    language_code: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(10)] }),
    difficulty_level: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(30)] }),
    status: new FormControl('DRAFT', {
      nonNullable: true, validators: [Validators.required, Validators.maxLength(30)],
    }),
    is_favorite: new FormControl(false, { nonNullable: true }),
  });

  ngOnInit(): void {
    this.search.valueChanges.pipe(
      debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef),
    ).subscribe((value) => {
      this.searchTerm.set(value.trim());
      this.resetPage();
    });
    this.typeFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.statusFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.favoritesFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.favoritesOnly.set(value);
        this.resetPage();
      });
    this.checkAuth();
  }

  can(permission: string): boolean {
    return this.principal()?.permissions.includes(permission) ?? false;
  }

  checkAuth(): void {
    this.authMode.set('checking');
    this.auth.me().subscribe({
      next: principal => this.signedIn(principal),
      error: (error: unknown) => {
        this.authMode.set('login');
        this.principal.set(null);
        if (error instanceof HttpErrorResponse && error.status !== 401) {
          this.loginError.set('Vérification de session impossible. Vérifie les conteneurs.');
        }
      },
    });
  }

  submitLogin(): void {
    if (this.loginForm.invalid || this.loggingIn()) return;
    this.loginError.set('');
    this.loggingIn.set(true);
    const credentials = this.loginForm.getRawValue();
    this.auth.login(credentials.username, credentials.password).pipe(
      finalize(() => this.loggingIn.set(false)),
    ).subscribe({
      next: principal => {
        this.loginForm.controls.password.reset();
        this.signedIn(principal);
      },
      error: (error: unknown) => {
        this.loginError.set(error instanceof HttpErrorResponse && error.status === 429
          ? 'Trop de tentatives. Réessaie après une minute.'
          : 'Connexion refusée. Vérifie les identifiants et le compte administrateur initial.');
      },
    });
  }

  logout(): void {
    this.auth.logout().subscribe({
      next: () => {
        this.principal.set(null);
        this.items.set([]);
        this.selected.set(null);
        this.authMode.set('login');
        this.loginForm.reset({ username: '', password: '' });
      },
      error: () => this.error.set('Déconnexion impossible. Réessaie.'),
    });
  }

  private signedIn(principal: LocalIdentity): void {
    this.principal.set(principal);
    this.authMode.set('active');
    this.loginError.set('');
    this.loadPage();
  }

  typeLabel(code: string): string {
    return knowledgeTypeLabel(code);
  }

  dateLabel(value: string): string {
    return new Date(value).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  resetFilters(): void {
    this.search.setValue('');
    this.favoritesFilter.setValue(false);
    this.typeFilter.setValue('');
    this.statusFilter.setValue('');
  }

  reload(): void {
    this.notice.set('');
    this.loadPage();
  }

  previousPage(): void {
    if (this.pageIndex() === 0) return;
    this.pageIndex.update((value) => value - 1);
    this.loadPage();
  }

  nextPage(): void {
    if (this.currentPage() >= this.pageCount()) return;
    this.pageIndex.update((value) => value + 1);
    this.loadPage();
  }

  createKnowledge(): void {
    if (!this.can('knowledge.create') || !this.mayLeaveEditor()) return;
    this.notice.set('');
    this.formError.set('');
    this.error.set('');
    this.selected.set(null);
    this.etag.set(null);
    this.confirmingDelete.set(false);
    this.editor.reset({
      knowledge_type: 'CODE_SNIPPET',
      title: '', content: '', description: '',
      language_code: '', difficulty_level: '', status: 'DRAFT', is_favorite: false,
    });
    this.editor.markAsPristine();
    this.mode.set('create');
  }

  openKnowledge(item: Knowledge): void {
    if (!this.mayLeaveEditor()) return;
    this.fetchDetail(item.knowledge_id);
  }

  refreshDetail(): void {
    const current = this.selected();
    if (current && window.confirm('Recharger la version enregistrée ? Les modifications non sauvegardées seront perdues.')) {
      this.fetchDetail(current.knowledge_id);
    }
  }

  beginEdit(): void {
    if (!this.can('knowledge.update')) return;
    const item = this.selected();
    if (!item) return;
    this.fillEditor(item);
    this.formError.set('');
    this.confirmingDelete.set(false);
    this.mode.set('edit');
  }

  cancelEdit(): void {
    this.mode.set('view');
    this.confirmingDelete.set(false);
    this.formError.set('');
    this.editor.markAsPristine();
  }

  saveKnowledge(): void {
    if ((this.mode() === 'create' && !this.can('knowledge.create')) ||
        (this.mode() === 'edit' && !this.can('knowledge.update'))) return;
    if (this.saving()) return;
    if (this.editor.invalid) {
      this.editor.markAllAsTouched();
      this.formError.set('Vérifie les champs obligatoires et les longueurs maximales.');
      return;
    }
    const value = this.editor.getRawValue();
    const payload: KnowledgeWrite = {
      knowledge_type: value.knowledge_type,
      title: value.title.trim(),
      content: value.content,
      description: value.description.trim() || null,
      language_code: value.language_code.trim() || null,
      difficulty_level: value.difficulty_level.trim() || null,
      status: value.status.trim(),
      is_favorite: value.is_favorite,
    };
    if (!payload.title || !payload.content.trim()) {
      this.formError.set('Le titre et le contenu ne peuvent pas être vides.');
      return;
    }
    this.formError.set('');
    this.notice.set('');
    const current = this.selected();
    const tag = this.etag();
    if (this.mode() === 'edit' && (!current || !tag)) {
      this.formError.set('Révision absente : recharge la fiche avant toute modification.');
      return;
    }
    this.saving.set(true);
    const operation = this.mode() === 'create'
      ? this.api.create(payload)
      : this.api.update(current!.knowledge_id, payload, tag!);
    operation.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (response) => {
        this.acceptSaved(response);
        this.notice.set(this.mode() === 'create' ? 'Connaissance créée.' : 'Modifications enregistrées.');
        this.mode.set('view');
        this.editor.markAsPristine();
        this.loadPage();
      },
      error: (error: unknown) => this.formError.set(this.errorMessage(error)),
    });
  }

  askDelete(): void {
    if (!this.can('knowledge.delete')) return;
    this.confirmingDelete.set(true);
    this.formError.set('');
  }

  cancelDelete(): void {
    this.confirmingDelete.set(false);
  }

  deleteKnowledge(): void {
    const item = this.selected();
    const tag = this.etag();
    if (!item || !tag || this.saving()) {
      this.formError.set('Révision absente : recharge la fiche avant toute suppression.');
      return;
    }
    this.saving.set(true);
    this.formError.set('');
    this.api.delete(item.knowledge_id, tag).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.selected.set(null);
        this.etag.set(null);
        this.confirmingDelete.set(false);
        this.mode.set('view');
        this.notice.set('Connaissance retirée de la liste (suppression logique).');
        if (this.pageIndex() > 0 && this.items().length === 1) this.pageIndex.update((value) => value - 1);
        this.loadPage();
      },
      error: (error: unknown) => this.formError.set(this.errorMessage(error)),
    });
  }

  private resetPage(): void {
    this.pageIndex.set(0);
    this.loadPage();
  }

  private loadPage(): void {
    const sequence = ++this.listSequence;
    this.busy.set(true);
    this.error.set('');
    const type = this.typeFilter.value;
    const status = this.statusFilter.value.trim();
    const q = this.searchTerm().slice(0, 100);
    this.api.list({
      skip: this.pageIndex() * PAGE_SIZE,
      limit: PAGE_SIZE,
      ...(type ? { knowledge_type: type } : {}),
      ...(status ? { status } : {}),
      ...(q ? { q } : {}),
      ...(this.favoritesOnly() ? { is_favorite: true } : {}),
    }).pipe(finalize(() => {
      if (sequence === this.listSequence) this.busy.set(false);
    })).subscribe({
      next: (page) => {
        // Ignore responses to superseded searches and filter changes.
        if (sequence !== this.listSequence) return;
        this.items.set(page.items);
        this.total.set(page.total);
      },
      error: (error: unknown) => {
        if (sequence !== this.listSequence) return;
        this.items.set([]);
        this.total.set(0);
        this.error.set(this.errorMessage(error));
      },
    });
  }

  private fetchDetail(id: string): void {
    this.detailLoading.set(true);
    this.formError.set('');
    this.error.set('');
    this.confirmingDelete.set(false);
    this.api.get(id).pipe(finalize(() => this.detailLoading.set(false))).subscribe({
      next: (response) => {
        const item = response.body;
        if (!item) {
          this.error.set('Réponse vide du service de connaissances.');
          return;
        }
        this.selected.set(item);
        this.etag.set(response.headers.get('ETag') ?? '"' + item.revision + '"');
        this.mode.set('view');
        this.editor.markAsPristine();
      },
      error: (error: unknown) => this.error.set(this.errorMessage(error)),
    });
  }

  private acceptSaved(response: HttpResponse<Knowledge>): void {
    const item = response.body;
    if (item) {
      this.selected.set(item);
      this.etag.set(response.headers.get('ETag') ?? '"' + item.revision + '"');
    }
  }

  private fillEditor(item: Knowledge): void {
    this.editor.reset({
      knowledge_type: item.knowledge_type,
      title: item.title,
      content: item.content,
      description: item.description ?? '',
      language_code: item.language_code ?? '',
      difficulty_level: item.difficulty_level ?? '',
      status: item.status,
      is_favorite: item.is_favorite,
    });
    this.editor.markAsPristine();
  }

  private mayLeaveEditor(): boolean {
    return this.mode() === 'view' || !this.editor.dirty ||
      window.confirm('Abandonner les modifications non enregistrées ?');
  }

  private errorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) return 'Une erreur inattendue est survenue.';
    switch (error.status) {
      case 0: return 'Connexion impossible. Vérifie que le frontend et la Gateway fonctionnent.';
      case 400: return 'Précondition de version invalide. Recharge la connaissance.';
      case 404: return 'Cette connaissance est introuvable ou a été supprimée.';
      case 412: return 'Conflit de modification (412) : une autre version existe. Recharge et compare avant de réessayer.';
      case 413: return 'Le contenu dépasse la limite de 1 Mio de la Gateway.';
      case 422: return 'Données refusées par le serveur (422). Vérifie le titre, le contenu et les champs.';
      case 428: return 'La révision est obligatoire (428). Recharge la connaissance.';
      case 502: return 'Le Knowledge Service ne répond pas à la Gateway (502).';
      case 503: return 'MongoDB ou le Knowledge Service est indisponible (503).';
      case 504: return 'Le Knowledge Service n’a pas répondu à temps (504).';
      default: return 'Échec de l’opération (HTTP ' + error.status + ').';
    }
  }
}
