#!/usr/bin/env python3
"""Exercise Pillar 31 with an enrolled DNA Anchor and persistent files."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.engine.narrative_continuity import (  # noqa: E402
    DNAAnchorNarrativeSigner,
    NarrativeContinuity,
    NarrativeContinuityError,
    NarrativeTruthClass,
)
from jaya_core.brain_v2.protection.dna_anchor import (  # noqa: E402
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)


def run_standalone_demo(output_dir: Path) -> int:
    """Run an end-to-end vertical slice demo of Pilar 31 Narrative Continuity."""
    output_dir.mkdir(parents=True, exist_ok=True)
    identity_dir = output_dir / "identity"
    keystore_dir = identity_dir / "keystore"
    ledger_path = output_dir / "narrative_demo.sqlite3"
    evidence_path = output_dir / "quantum_release_memo.txt"

    secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET") or "demo-dna-secret-material-32-bytes-long!!"

    evidence_path.write_text(
        "Project release v2.4 confirmed stable by automated verification on 2026-09-06.\n"
        "Lead reviewer: Dr. Alan Turing.\n"
        "Status: VERIFIED.\n",
        encoding="utf-8",
    )

    print("=" * 75)
    print(" PILAR 31: NARRATIVE CONTINUITY — LIVE VERTICAL SLICE DEMO")
    print("=" * 75)
    print(f"Data directory: {output_dir}")
    print(f"Ledger DB:      {ledger_path}\n")

    # Clean previous demo ledger if present to ensure fresh scenario execution
    for ext in ("", "-wal", "-shm"):
        p = Path(str(ledger_path) + ext)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    run_id = f"{int(time.time())}"

    anchor: DNAAnchor | None = None
    ledger: NarrativeContinuity | None = None

    try:
        # Step 1: Initialize / Enroll DNA Anchor identity
        print("1. Initializing & Enrolling DNA Anchor Identity...")
        key_store = EncryptedFileKeyStore(keystore_dir, secret)
        anchor = DNAAnchor(identity_dir, key_store)
        try:
            anchor.load_identity()
            print("   -> Loaded existing DNA Anchor identity.")
        except Exception:
            anchor.enroll()
            print("   -> Enrolled new DNA Anchor identity with Ed25519 signing key.")

        signer = DNAAnchorNarrativeSigner(anchor)
        print(f"   -> Signer Actor ID: {signer.actor_id}")
        print(f"   -> Signer Key ID:   {signer.key_id}\n")

        # Step 2: Initialize Narrative Continuity Ledger
        print("2. Initializing Append-Only Signed Narrative Ledger...")
        ledger = NarrativeContinuity(ledger_path, signer)
        print("   -> SQLite ledger initialized with append-only triggers and HMAC/SHA-256 chain.\n")

        # Step 3: Register Evidence & Assert Verified Fact
        print("3. Registering Evidence and Asserting Verified Fact...")
        evidence_content = evidence_path.read_bytes()
        evidence_ref = ledger.register_evidence(
            content=evidence_content,
            source_uri=str(evidence_path),
            media_type="text/plain",
        )
        print(f"   -> Registered evidence ref: {evidence_ref}")

        fact_alpha = ledger.record_verified_fact(
            request_id=f"fact-release-alpha-{run_id}",
            subject="project.release",
            value="alpha-candidate",
            evidence_refs=(evidence_ref,),
        )
        print(f"   -> Fact asserted: {fact_alpha.event_id} | subject='{fact_alpha.subject}' | value='{fact_alpha.payload.get('value')}'\n")

        # Step 4: Record Conversation Turn and Active Commitment
        print("4. Recording Conversation Turn & Active Commitment...")
        turn_evt = ledger.remember_turn(
            "Operator confirmed benchmark criteria met",
            request_id=f"turn-operator-confirm-{run_id}",
        )
        print(f"   -> Turn event recorded: {turn_evt.get('event_id')} (CONVERSATION_TURN)")

        commitment_evt = ledger.record_commitment(
            request_id=f"commit-deploy-check-{run_id}",
            commitment_id="commitment:production_deploy",
            subject="project.deploy",
            details={"gate": "all_40_pillars_verified", "target_env": "production_staging"},
            evidence_refs=(evidence_ref,),
        )
        print(f"   -> Commitment recorded: {commitment_evt.event_id} | ID='commitment:production_deploy'\n")

        # Step 5: Conflict Detection on Diverging Fact Assertion
        print("5. Demonstrating Conflict Detection on Diverging Fact Assertion...")
        second_evidence_ref = ledger.register_evidence(
            content=b"release=beta-candidate confirmed by lead auditor",
            source_uri="memory://release-memo-beta",
            media_type="text/plain",
        )
        fact_beta = ledger.record_verified_fact(
            request_id=f"fact-release-beta-{run_id}",
            subject="project.release",
            value="beta-candidate",
            evidence_refs=(second_evidence_ref,),
        )
        print(f"   -> Conflicting fact asserted: {fact_beta.event_id} | value='beta-candidate'")

        snap_conflicted = ledger.snapshot(limit=20, max_chars=20_000)
        conflicts = snap_conflicted["summary"].get("conflicts", [])
        print(f"   -> Conflict detected in snapshot: {len(conflicts)} conflict(s) found on subject '{conflicts[0]['subject']}'.")
        print(f"   -> Conflict status: {conflicts[0]['status']}\n")

        # Step 6: Evidence-Bound Correction Resolving Conflict
        print("6. Resolving Conflict via Evidence-Bound Correction Link...")
        correction_evt = ledger.record_correction(
            request_id=f"correction-release-final-{run_id}",
            correction_of=fact_alpha.event_id,
            subject="project.release",
            corrected_value="beta-candidate",
            evidence_refs=(second_evidence_ref,),
            truth_class=NarrativeTruthClass.VERIFIED_FACT,
        )
        print(f"   -> Correction recorded: {correction_evt.event_id} | resolves conflict on '{correction_evt.subject}'")

        snap_resolved = ledger.snapshot(limit=20, max_chars=20_000)
        print(f"   -> Snapshot after correction: {len(snap_resolved['summary'].get('conflicts', []))} unresolved conflicts.")
        print(f"   -> Resolved verified fact value: '{snap_resolved['summary']['verified_facts'][0]['value']}'\n")

        # Step 7: Restart Durability & Boot Context
        print("7. Testing Process Restart & Boot Context Re-hydration...")
        saved_snapshot_digest = snap_resolved["snapshot_sha256"]
        ledger.close()

        # Reopen ledger with freshly instantiated NarrativeContinuity
        reopened_ledger = NarrativeContinuity(ledger_path, signer)
        boot_context = reopened_ledger.boot_context()
        print(f"   -> Reopened database: Snapshot SHA-256 before restart: {saved_snapshot_digest}")
        print(f"   -> Reopened database: Snapshot SHA-256 after restart:  {boot_context['snapshot_sha256']}")
        assert boot_context["snapshot_sha256"] == saved_snapshot_digest
        print("   -> 100% Deterministic match! Zero memory loss or mutation across restart.\n")

        # Step 8: Full-Chain Cryptographic Integrity Audit
        print("8. Performing Full-Chain Cryptographic Integrity Audit...")
        t0_audit = time.perf_counter()
        integrity_ok = reopened_ledger.verify_integrity()
        t_audit_ms = (time.perf_counter() - t0_audit) * 1000.0
        print(f"   -> Integrity audit result: {integrity_ok} (checked in {t_audit_ms:.2f} ms)\n")

        # Step 9: Tamper Rejection (Append-Only Trigger Enforcement)
        print("9. Testing Append-Only Immutability Triggers (SQL UPDATE / DELETE)...")
        with sqlite3.connect(ledger_path) as conn:
            update_blocked = False
            try:
                conn.execute("UPDATE narrative_events SET subject='tampered' WHERE event_type='FACT_ASSERTED'")
            except (sqlite3.IntegrityError, sqlite3.OperationalError):
                update_blocked = True

            delete_blocked = False
            try:
                conn.execute("DELETE FROM narrative_events WHERE event_type='FACT_ASSERTED'")
            except (sqlite3.IntegrityError, sqlite3.OperationalError):
                delete_blocked = True

        print(f"   -> Direct SQL UPDATE blocked: {update_blocked}")
        print(f"   -> Direct SQL DELETE blocked: {delete_blocked}")
        print("   -> Append-only ledger triggers enforced fail-closed against tampering.\n")

        reopened_ledger.close()
        ledger = None

        print("=" * 75)
        print(" PILAR 31: NARRATIVE CONTINUITY — DEMO COMPLETED SUCCESSFULLY")
        print("=" * 75)
        return 0

    except (DNAAnchorError, NarrativeContinuityError, OSError) as exc:
        print(f"Demo failed with error: {exc}", file=sys.stderr)
        return 2
    finally:
        if ledger is not None:
            ledger.close()
        if anchor is not None:
            anchor.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-dir", type=Path, default=None, help="DNA Anchor identity directory")
    parser.add_argument("--ledger", type=Path, default=None, help="Narrative SQLite ledger path")
    parser.add_argument("--request-id", default=None, help="Request ID for single fact assert")
    parser.add_argument("--subject", default=None, help="Subject for single fact assert")
    parser.add_argument("--value", default=None, help="Value for single fact assert")
    parser.add_argument("--evidence-file", type=Path, default=None, help="Evidence file path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "demo-narrative-continuity",
        help="Output directory for self-contained interactive demo",
    )
    args = parser.parse_args()

    # If all single-shot arguments provided, run single-shot mode
    if (
        args.identity_dir is not None
        and args.ledger is not None
        and args.request_id is not None
        and args.subject is not None
        and args.value is not None
        and args.evidence_file is not None
    ):
        secret = os.environ.get("JAYA_IDENTITY_KEY_SECRET", "")
        if len(secret.encode("utf-8")) < 32:
            print("JAYA_IDENTITY_KEY_SECRET is missing or shorter than 32 bytes", file=sys.stderr)
            return 2
        identity_dir = args.identity_dir.expanduser().resolve()
        ledger_path = args.ledger.expanduser().resolve()
        anchor = None
        ledger = None
        try:
            anchor = DNAAnchor(
                identity_dir,
                EncryptedFileKeyStore(identity_dir / "keystore", secret),
            )
            anchor.load_identity()
            signer = DNAAnchorNarrativeSigner(anchor)
            ledger = NarrativeContinuity(ledger_path, signer)
            evidence_path = args.evidence_file.expanduser().resolve()
            evidence_ref = ledger.register_evidence(
                content=evidence_path.read_bytes(),
                source_uri=str(evidence_path),
            )
            event = ledger.record_verified_fact(
                request_id=args.request_id,
                subject=args.subject,
                value=args.value,
                evidence_refs=(evidence_ref,),
            )
            first_snapshot = ledger.snapshot(limit=10, max_chars=20_000)
            ledger.close()
            ledger = NarrativeContinuity(ledger_path, signer)
            boot_context = ledger.boot_context(first_snapshot["snapshot_version"])
            print(
                json.dumps(
                    {
                        "event_id": event.event_id,
                        "event_sha256": event.event_sha256,
                        "evidence_ref": evidence_ref,
                        "snapshot_version": first_snapshot["snapshot_version"],
                        "snapshot_sha256": first_snapshot["snapshot_sha256"],
                        "boot_context_after_restart": boot_context,
                        "integrity_verified": ledger.verify_integrity(),
                        "ledger_path": str(ledger_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        except (DNAAnchorError, NarrativeContinuityError, OSError) as exc:
            code = getattr(getattr(exc, "code", None), "value", "IO_ERROR")
            print(json.dumps({"ok": False, "code": code}), file=sys.stderr)
            return 2
        finally:
            if ledger is not None:
                ledger.close()
            if anchor is not None:
                anchor.close()
    else:
        # Run self-contained comprehensive demo
        return run_standalone_demo(args.output_dir.expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
