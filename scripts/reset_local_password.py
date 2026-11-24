"""Reset an existing application password through the running Supervisor.

Local Docker operator access is required. Passwords travel only over stdin;
the existing revision/mutex/session-revocation implementation is reused.
"""
import argparse
import getpass
import json
from pathlib import Path
import subprocess
import warnings

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = r"""
const { MongoClient } = require('mongodb');
const { createUserManagement } = require('/app/src/identity-users');
const { usernameKey } = require('/app/src/identity-sessions');
(async () => {
  if (process.env.SUPERVISOR_IDENTITY_MODE !== 'active') throw Error('Active identity required');
  let input = '';
  for await (const chunk of process.stdin) {
    input += chunk;
    if (input.length > 8192) throw Error('Invalid input');
  }
  const { username, password } = JSON.parse(input);
  const key = usernameKey(username);
  if (!key) throw Error('Invalid username');
  const client = new MongoClient(`mongodb://${process.env.MONGODB_HOST}:${process.env.MONGODB_PORT || 27017}/`, {
    auth: {username: process.env.MONGODB_USERNAME, password: process.env.MONGODB_PASSWORD},
    authSource: process.env.MONGODB_AUTH_SOURCE, serverSelectionTimeoutMS: 3000,
  });
  try {
    await client.connect();
    const db = client.db(process.env.MONGODB_DATABASE);
    const user = await db.collection('users').findOne({username_key:key,account_status:'ACTIVE',deleted_at:null});
    if (!user) throw Error('Active account not found');
    const revision = user.revision ?? 1;
    if (!Number.isSafeInteger(revision) || revision < 1 || revision >= Number.MAX_SAFE_INTEGER) throw Error('Invalid revision');
    await createUserManagement(db).mutate(user._id, revision, user._id, {password}, 'password');
    process.stdout.write('Password updated; existing sessions revoked\n');
  } finally { await client.close(); }
})().catch(() => {
  process.stderr.write('Password reset refused or unavailable\n');
  process.exitCode = 1;
});
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--project", default="devknowledge")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Nouveau mot de passe : ")
            confirmation = getpass.getpass("Confirmer le mot de passe : ")
    except (getpass.GetPassWarning, EOFError):
        raise SystemExit("Une saisie masquée est requise : lancer depuis un terminal interactif.") from None
    if password != confirmation:
        raise SystemExit("Les mots de passe sont différents ; aucun changement effectué.")
    if not 12 <= len(password) <= 256 or not password.strip():
        raise SystemExit("Le mot de passe doit contenir entre 12 et 256 caractères.")
    command = ["docker", "compose", "--env-file", str(args.env_file.resolve()),
               "-p", args.project, "-f", str(ROOT / "compose.yaml"),
               "exec", "-T", "supervisor", "node", "-e", NODE_SCRIPT]
    try:
        result = subprocess.run(command, cwd=ROOT,
                                input=json.dumps({"username": args.username, "password": password}),
                                text=True, encoding="utf-8", capture_output=True, check=False)
    except OSError:
        raise SystemExit("Docker est indisponible ; aucun changement effectué.") from None
    if result.returncode:
        raise SystemExit("Réinitialisation refusée ou indisponible. Vérifier le nom du compte actif et le Superviseur. En cas de concurrence, réessayer.")
    print("Mot de passe modifié ; les anciennes sessions du compte sont révoquées.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Opération interrompue.") from None
