cmake_minimum_required(VERSION 3.18)

project(jaya_native LANGUAGES CXX)

option(JAYA_BUILD_TRUSTED_RUST "Build the Rust trusted artifact gate" ON)
option(JAYA_NATIVE_OPTIMIZE_HOST "Enable host-specific CPU instructions" OFF)
set(JAYA_RUST_TARGET "" CACHE STRING "Optional Cargo target triple")

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(JAYA_NATIVE_OUTPUT_DIR "${CMAKE_BINARY_DIR}/lib")

add_library(jaya_compute SHARED
    compute/src/jaya_compute.cpp
)
target_include_directories(jaya_compute PUBLIC compute/include)
target_compile_definitions(jaya_compute PRIVATE JAYA_COMPUTE_BUILD=1)

if(MSVC)
    target_compile_options(jaya_compute PRIVATE /O2 /W4 /permissive-)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(jaya_compute PRIVATE -O3 -Wall -Wextra -Wpedantic)
    if(MINGW)
        target_link_options(jaya_compute PRIVATE -static-libgcc -static-libstdc++)
    endif()
    if(JAYA_NATIVE_OPTIMIZE_HOST)
        target_compile_options(jaya_compute PRIVATE -march=native)
    endif()
endif()

set_target_properties(jaya_compute PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${JAYA_NATIVE_OUTPUT_DIR}"
    RUNTIME_OUTPUT_DIRECTORY "${JAYA_NATIVE_OUTPUT_DIR}"
    ARCHIVE_OUTPUT_DIRECTORY "${JAYA_NATIVE_OUTPUT_DIR}"
)

if(JAYA_BUILD_TRUSTED_RUST)
    find_program(CARGO_EXECUTABLE cargo REQUIRED)
    set(JAYA_TRUSTED_MANIFEST "${CMAKE_CURRENT_SOURCE_DIR}/trusted/Cargo.toml")
    set(JAYA_CARGO_TARGET_DIR "${CMAKE_BINARY_DIR}/cargo")
    set(JAYA_CARGO_BUILD_ARGS
        build --release --manifest-path "${JAYA_TRUSTED_MANIFEST}"
    )
    if(JAYA_RUST_TARGET)
        list(APPEND JAYA_CARGO_BUILD_ARGS --target "${JAYA_RUST_TARGET}")
        set(JAYA_CARGO_RELEASE_DIR "${JAYA_CARGO_TARGET_DIR}/${JAYA_RUST_TARGET}/release")
    else()
        set(JAYA_CARGO_RELEASE_DIR "${JAYA_CARGO_TARGET_DIR}/release")
    endif()
    if(JAYA_RUST_TARGET MATCHES "windows")
        set(JAYA_TRUSTED_SOURCE "${JAYA_CARGO_RELEASE_DIR}/jaya_trusted.dll")
    else()
        set(JAYA_TRUSTED_SOURCE
            "${JAYA_CARGO_RELEASE_DIR}/${CMAKE_SHARED_LIBRARY_PREFIX}jaya_trusted${CMAKE_SHARED_LIBRARY_SUFFIX}"
        )
    endif()
    set(JAYA_TRUSTED_OUTPUT
        "${JAYA_NATIVE_OUTPUT_DIR}/${CMAKE_SHARED_LIBRARY_PREFIX}jaya_trusted${CMAKE_SHARED_LIBRARY_SUFFIX}"
    )

    add_custom_command(
        OUTPUT "${JAYA_TRUSTED_OUTPUT}"
        COMMAND "${CMAKE_COMMAND}" -E env
            "CARGO_TARGET_DIR=${JAYA_CARGO_TARGET_DIR}"
            "${CARGO_EXECUTABLE}" ${JAYA_CARGO_BUILD_ARGS}
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${JAYA_NATIVE_OUTPUT_DIR}"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${JAYA_TRUSTED_SOURCE}" "${JAYA_TRUSTED_OUTPUT}"
        DEPENDS
            "${JAYA_TRUSTED_MANIFEST}"
            "${CMAKE_CURRENT_SOURCE_DIR}/trusted/src/lib.rs"
        COMMENT "Building the JAYA Rust trusted provider"
        VERBATIM
    )
    add_custom_target(jaya_trusted ALL DEPENDS "${JAYA_TRUSTED_OUTPUT}")
endif()
