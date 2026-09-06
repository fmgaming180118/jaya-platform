"""Fail-closed static security and truthfulness gate for JAYA Android."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "packages" / "jaya-android"


@dataclass(frozen=True)
class Rule:
    path: str
    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


RULES = (
    Rule(
        "app/src/main/AndroidManifest.xml",
        required=(
            'android:allowBackup="false"',
            'android:usesCleartextTraffic="false"',
        ),
        forbidden=(
            "MANAGE_EXTERNAL_STORAGE",
            "WRITE_EXTERNAL_STORAGE",
            'android:allowBackup="true"',
        ),
    ),
    Rule(
        "app/src/debug/res/xml/network_security_config_debug.xml",
        required=(
            '<base-config cleartextTrafficPermitted="false"',
            "10.0.2.2",
            "127.0.0.1",
            "localhost",
        ),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/data/remote/NetworkModule.kt",
        required=(
            'header("Authorization", "Bearer $it")',
            "BuildConfig.DEBUG && localDebugHost",
            "HttpLoggingInterceptor.Level.NONE",
        ),
        forbidden=(
            "HttpLoggingInterceptor.Level.BODY",
            'const val DEFAULT_JAYA_API_URL = "http://',
        ),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/data/remote/JayaApiService.kt",
        required=('@POST("v1/chat")',),
        forbidden=("auto-upgrade", "thesis/analyze", "evolution/status"),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/data/remote/JayaModels.kt",
        required=('@param:Json(name = "message")',),
        forbidden=(
            '@param:Json(name = "prompt")',
            "workspace_id",
            "use_local_rag",
        ),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/security/SqliteCipherVault.kt",
        required=("KeystoreSecretStore", "getOrCreateRandom"),
        forbidden=("JAYA_DEFAULT", "secretKey.encoded"),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/security/PqcEncryptedBackup.kt",
        required=(
            "PqcProviderUnavailableException",
            "provider ?: throw",
            "selfTest()",
        ),
        forbidden=(
            "PQC-Dilithium3-AES256",
            "MessageDigest.getInstance",
            "Simulasi",
        ),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/ui/settings/SettingsViewModel.kt",
        required=("KeystoreSecretStore", "deletePreference(LEGACY_API_KEY_PREFERENCE)"),
        forbidden=(
            "JAYA_SOVEREIGN_PASSPHRASE",
            'savePreference("API_KEY"',
        ),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/data/core/OnDeviceNeuralGenerator.kt",
        required=("Legacy template generation is disabled",),
        forbidden=("java.util.Random", "coreKnowledgeMap", "prefixes = listOf"),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/skills/SearchSkill.kt",
        required=("SEARCH_PROVIDER_UNAVAILABLE", "https"),
        forbidden=("Simulasi", "peningkatan efisiensi sebesar 40%"),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/vision/SmartDocumentScanner.kt",
        required=("OcrEngine", "DocumentEmbeddingEncoder"),
        forbidden=("simulatedExtractedText", "dummyVector", "confidence = 0.98f"),
    ),
    Rule(
        "app/src/main/java/com/example/jaya/data/network/AutoSyncManager.kt",
        required=("EcosystemSyncAdapter", "SYNC_ADAPTER_UNAVAILABLE"),
        forbidden=("downloadedPatches = 1", "getEvolutionStatus"),
    ),
)


def audit() -> list[str]:
    failures: list[str] = []
    for rule in RULES:
        path = ANDROID / rule.path
        if not path.is_file():
            failures.append(f"missing file: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for required in rule.required:
            if required not in text:
                failures.append(
                    f"{path.relative_to(ROOT)}: missing invariant {required!r}"
                )
        for forbidden in rule.forbidden:
            if forbidden in text:
                failures.append(
                    f"{path.relative_to(ROOT)}: forbidden pattern {forbidden!r}"
                )
    return failures


def main() -> int:
    failures = audit()
    if failures:
        print("Android security audit FAILED:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Android security audit PASSED: {len(RULES)} invariant groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
