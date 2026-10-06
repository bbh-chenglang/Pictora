# Pictora generated-image R2 storage

R2 is opt-in and archives only newly inserted `generated` images. Existing images
and `reference` images are not queued or migrated. The local SQLite BLOB is retained
as a fallback. R2 uploads and SHA-256 readback verification run outside the generation
request. Stable object keys, persisted leases and bounded retries survive restarts.
No model generation is retried by the storage worker.

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

The existing authenticated history-image route checks ownership before any R2 read.
It prefers verified R2 objects and falls back to local data on missing objects or
storage errors. No bucket/public-domain access change is required. Thumbnails and
reference-image editing retain their existing local behavior.

Deleting a new image detaches its outbox via ON DELETE SET NULL. The worker then
removes only its recorded R2 object; records for existing historical images are absent.

Inspect status without reading images/prompts/credentials:

```sql
SELECT status, COUNT(*) FROM r2_image_uploads GROUP BY status;
```

Disable by setting R2_ENABLED=false and recreating backend. All local images remain
readable; pending uploads remain persisted for a later re-enable. Do not remove the
original image BLOBs without a separate, explicitly requested retention migration.

## Coexistence with video storage

Compose reads optional root `.env` followed by optional `.env.r2`. Shared
`R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` are passed through these files; they
are not overwritten by empty interpolation defaults. When both files provide
these credentials, `.env.r2` takes precedence so existing image archival keeps
its configured identity.

Image storage continues using `R2_ENDPOINT`, `R2_BUCKET`, and `R2_PREFIX`.
Video storage uses `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, and `R2_KEY_PREFIX`.
They may use the same private bucket with different prefixes. Set both sets of
destination fields when enabling both features. No historical-image backfill,
public bucket, or lifecycle-policy change is performed during this deployment.
