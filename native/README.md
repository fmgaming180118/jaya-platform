# JAYA native providers

This directory contains optional first-party native providers. Python remains
the control plane; pillars reach these libraries through versioned C ABI
contracts.

- `jaya_compute`: C++20 CPU kernels for measured binary and ternary hot paths.
- `jaya_trusted`: Rust validation gate for identifiers/artifact layouts, the
  bounded P15 `JPR1` policy-rule evaluator, and the P20 `JPV1` privacy-scope
  evaluator, plus the P18 `JZT1` authorization-scope evaluator. P18/P20 ABIs
  never receive payload/plaintext, keys, signatures, or ciphertext.

Base Python does not require a native compiler. A native build places both
shared libraries in `native/build/lib`:

```bash
cmake -S native -B native/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build native/build
```

Set `JAYA_NATIVE_LIBRARY_DIR` to that directory when it is outside the normal
repository build location. Set `JAYA_COMPUTE_PROVIDER=native-cpu` or
`JAYA_TRUSTED_PROVIDER=trusted-rust` to require a provider. Set
`JAYA_POLICY_PROVIDER=trusted-rust` to require native P15 rule evaluation. Strict
selection fails closed when unavailable. Set
`JAYA_PRIVACY_PROVIDER=trusted-rust` to require native P20 scope evaluation.
Set `JAYA_ZERO_TRUST_PROVIDER=trusted-rust` to require native P18 authorization
scope evaluation.
The default `auto` mode selects a built native library and otherwise uses the
labeled Python reference path.

For a reproducible isolated toolchain:

```bash
docker build -f native/Dockerfile.toolchain -t jaya-native-toolchain:bookworm native
docker run --rm -v "$PWD:/workspace" jaya-native-toolchain:bookworm \
  sh -lc 'cmake -S native -B native/build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build native/build'
```

The same image can cross-build self-contained Windows x86_64 DLLs:

```bash
docker run --rm -v "$PWD:/workspace" jaya-native-toolchain:bookworm \
  cmake -S native -B native/build-windows -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE=/workspace/native/cmake/mingw-x86_64.cmake \
  -DJAYA_RUST_TARGET=x86_64-pc-windows-gnu
docker run --rm -v "$PWD:/workspace" jaya-native-toolchain:bookworm \
  cmake --build native/build-windows
```

Cross-compilation is not treated as runtime verification. The strict Windows
test lane loads the DLLs through Windows Python.

No CUDA, ROCm, OpenVINO, Metal, or mobile SDK is linked by this profile.
