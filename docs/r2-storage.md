# Pictora generated-image R2 storage

R2 is opt-in and stores newly inserted `generated` images. The local SQLite BLOB
is temporary: the worker uploads the original, downloads it for size and SHA-256
verification, then atomically marks the object ready and clears the local original.
Failed uploads or failed verification retain local bytes for retry. Stable object
keys, persisted leases and bounded retries survive restarts. No model generation
is retried by the storage worker. Reference images remain local.

Create a root-private `.env.r2` beside `compose.yaml` (never commit it):

```dotenv
R2_ENABLED=true
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET=<bucket>
R2_ACCESS_KEY_ID=<access-key-id>
R2_SECRET_ACCESS_KEY=<secret-access-key>
R2_PREFIX=pictora/generated
```

Requires Compose >=2.24 for optional env_file. Rebuild/recreate only `backend`,
preserving APP_VERSION and all existing environment values. Drain active generation
tasks first. The startup migration adds an outbox table; it does not modify historical
image BLOBs. Preserve the data volume and an image/source rollback snapshot.

The authenticated history-image route checks ownership before any R2 read. Local
data remains readable while an upload is pending. Once the local original is cleared,
R2 errors return HTTP 503 with Retry-After rather than an empty image. Cached local
thumbnails remain available; missing thumbnails and image-to-video references can
read originals from R2. No bucket/public-domain access change is required.

Deleting a new image detaches its outbox via ON DELETE SET NULL. The worker then
removes only its recorded R2 object; records for existing historical images are absent.

Inspect status without reading images/prompts/credentials:

```sql
SELECT status, COUNT(*) FROM r2_image_uploads GROUP BY status;
```

Disabling R2 pauses uploads and makes remote-only originals unavailable. Keep the
configured bucket and credentials accessible after migrating. Restoring old code
alone does not restore cleared originals; use a compatible reader or restore the
database backup with appropriate handling of newer data.

## Explicit historical migration

Startup does not scan historical images. After an authorized database backup, run
inside the backend container:

```sh
python -m app.migrate_generated_images
```

The command queues existing generated images one at a time, preserves existing
object keys, and reverifies previously archived originals before clearing their
local bytes. It is resumable and uses the same leased jobs as the background worker.
References, users, projects, history records, and thumbnails are preserved. Progress
reports include remaining local originals and bytes. No paid model calls are made.

SQLite reuses freed pages but does not automatically shrink its file. To reclaim
disk space immediately, drain active tasks and stop the backend before running
SQLite VACUUM, then restart and verify the backend and web proxy. Keep only the
latest verified deployment backup according to the administrator's retention policy.

## Coexistence with video storage

Compose reads optional root `.env` followed by optional `.env.r2`. Shared
`R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` are passed through these files; they
are not overwritten by empty interpolation defaults. When both files provide
these credentials, `.env.r2` takes precedence so existing image archival keeps
its configured identity.

Image storage continues using `R2_ENDPOINT`, `R2_BUCKET`, and `R2_PREFIX`.
Video storage uses `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, and `R2_KEY_PREFIX`.
They may use the same private bucket with different prefixes. Set both sets of
destination fields when enabling both features. Historical backfill is explicitly
invoked; bucket access and lifecycle policies are managed separately.
