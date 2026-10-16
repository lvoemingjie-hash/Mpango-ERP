# Product Images: Private Storage and Paired Recovery

Implementation candidate only. No production change or recovery acceptance is
implied by this document. Preserve the existing DB authority/role contract.

## Storage Preparation

The image feature is disabled when PRODUCT_IMAGE_ROOT is empty. Existing catalog
and cash ordering remain usable. Provision a dedicated persistent private mount
outside both webroots, owned by the actual backend mpango UID, mode 0700. Files
are 0600. Confirm UID/mount/capacity on the deployment target before enabling;
never resolve a mismatch using root runtime, 0777, or broader database grants.
The candidate Compose volume is not an authorization to operate a live VPS.

Before enabling images, the authorized DB owner prepares an independently
identified database/cluster target and assigns a fresh random UUID as that
database's comment, exactly `mpango-media-v1:<canonical UUID>`. Refuse an existing
unrelated comment; do not overwrite operational metadata to force enablement.
This is operator metadata, not a runtime grant, tenant object or secret. Record
the approved cluster/resource identity separately. With the same actual app
connection, query `services.product_image_storage.DATABASE_IDENTITY_SQL` and call
`MediaStore.initialize_binding(identity)` against the verified EMPTY 0700 root.
It takes the media lease, exclusively creates a 0600 media-binding.json and
binds the pairing nonce, actual server address/port, DB name/OID and root
device/inode. Only the operator does this; API and GC NEVER adopt a root.
They query pg_catalog (not a session-settable GUC or caller-provided identity)
and require exact equality before accessing files. A copied/restored database
comment alone cannot rebind a different DB OID/endpoint/root inode.

The preparation operator and DB owner remain trusted. This is not a defense
against a privileged operator deliberately forging both paired sides or
replacing a cluster at an identical endpoint with identical catalog identities.
Every new/restored cluster is a NEW target: approve it, assign a NEW nonce,
initialize a NEW empty root, then restore only the immutable tenant subtrees.
Never copy the old media-binding.json/media.lock onto a new root. Include the
source binding and target rebind receipt in the paired backup/recovery record.
No permission is added to the app or migrator by this procedure.

The authoritative tree is tenant UUID / product UUID / immutable version UUID /
thumb.webp, detail.webp, manifest.json. Current references and independent
tombstone revisions live in tenant-local catalog_product_images. Neither the
directories nor manifests grant API access: each new GET checks the live user,
tenant/binding/product visibility and the current DB pointer. Never expose this
tree through nginx alias/static hosting. Never put Bearer tokens in URLs.

## Backup: One Database Snapshot Plus Referenced Files

1. Register exact source IDs, image root identity, private destination, backup ID
   and operator authority. Supply credentials through an approved private
   service/env mechanism, never argv or public logs. Global role attributes and
   memberships are prepared separately from the database dump; a DB dump is not
   proof of equivalent cluster identity.
2. Hold an exclusive flock on the existing root media.lock, the SAME lease used
   by upload/delete/GC, until the paired backup completes. Do not replace the
   lock inode. This pauses image writes only; orders/cash use no media lease.
3. Establish one REPEATABLE READ database snapshot. Export that snapshot and run
   pg_dump against it while the exporting transaction remains open. Query all
   current media references/revisions within that same snapshot, not from a
   later connection without the exported snapshot.
4. Copy exactly every referenced immutable version's two files and manifest to
   the private backup. Verify file identity, type, size and SHA-256 against the
   frozen DB metadata. Missing/corrupt files make this backup incomplete. Do not
   delete ambiguous-commit/orphan versions during backup.
5. Seal the DB dump, referenced-file list, source head/schema version and file
   hashes under the same backup ID. Only then finish the snapshot and release
   media.lock. Retention policy/owner must be agreed before live activation.
   Backups contain private media and account data and are not public artifacts.

## Fresh Restore and Negative Controls

1. Use new task-owned DB/media targets, exact resource IDs and role preparation;
   never restore over live or another task's resources. Restore the DB at the
   frozen revision and immutable media tree with the confirmed non-root UID and
   0700/0600 modes. Perform the explicit new-target pairing above; do not adopt
   a root from an arbitrary DSN. Check each reference has both matching variants.
2. With real JWTs, read merchant and retailer images, reject a different tenant,
   inactive binding and old version; re-login must retain the same revision.
   Preserve a separate no-image/tombstone product as a positive control.
3. Deliberately remove one owned restore-copy file and separately corrupt one
   owned copy. The reference/hash check must say IMAGE_RECOVERY_INCOMPLETE.
   Placeholder rendering and successful cash ordering do NOT turn that into a
   complete-media recovery PASS. Restore the copies from the sealed backup and
   reverify their original hashes; never mutate the backup/source to run controls.
4. Compare SKU identity/package/price revisions, order snapshots and economic
   projections before/after. Record actual runtime head/roles and limitations.
   Preserve failures and destroy only explicitly registered disposable targets.

## Conservative Orphan Reconciliation

Use backend/scripts/reconcile_product_image_files.py with the approved root and
tenant, IMAGE_RECONCILE_DATABASE_URL in private environment, first WITHOUT
--execute. It takes the same cross-worker lease, queries live current pointers,
and recognizes only attributed version manifests with verified variant hashes.
Only non-current versions older than 24 hours may be removed on explicit execute.
Unknown files/pending directories remain for precise operator investigation;
neither filename patterns nor mtime alone establish deletion ownership. DB or
identity failure refuses cleanup. No prune, wildcard deletion or outside roots.

Missing/conflicting media-binding.json or an actual DB identity mismatch refuses
even dry-run before walking files; execute never reaches unlink in that case.
Before enabling execute, test a second valid DB with the SAME tenant UUID/schema
but a different current pointer and prove the original root's bytes unchanged.

## Request I/O Ownership

All root/lock opening, binding reads, capacity scans, publication/fsync and image
reads/hashes run in four fixed worker threads, with four non-waiting admission
slots (no unbounded submission queue). The request waits at most five seconds
per storage operation. A timed-out/cancelled await does NOT stop a kernel call.
Its worker retains the slot and root/flock until the I/O really returns AND the
request transaction ends. No worker writes DB state. Pointer flush occurs only
after successful publication has completed; timeout/cancel rolls back the DB,
so a late immutable publication is an orphan, never a new current pointer.
On an indefinitely stuck local disk, slots stay occupied and further media
requests refuse rather than spawn more workers. Operator storage/process
recovery is then required; no hard kernel-I/O termination is claimed. This
contract excludes network filesystems. Independent quote/cash requests use no
media executor or lease. Read operations obey the same timeout/owner discipline.

Transient inputs use anonymous descriptors. Failed/uncertain DB commits may
leave immutable orphan versions: retain until the live pointer is known and the
grace window and ownership checks permit deletion. Disk/quota gates bound this
failure mode; never delete the last/current version to make room for an upload.
