cmake_minimum_required(VERSION 3.4.1)

# Opt-in only: Android identity/signing stays Debug, native code uses the
# standard optimized-with-symbols configuration. AGP hashes this extra option
# into a separate native graph, so ordinary debugger-friendly builds remain.
option(SEOUL_DS_OPTIMIZED_NATIVE "Build an optimized native core for the development-signed alpha" OFF)
if(SEOUL_DS_OPTIMIZED_NATIVE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Native build configuration" FORCE)
endif()

project(melonDS-android-frontend)

# Keep native builds usable alongside the Kotlin/lint workers on modest CI hosts.
# Ninja's default (CPU count + 2) can otherwise exhaust memory in this large core.
set_property(GLOBAL PROPERTY JOB_POOLS seoul_compile=1 seoul_link=1)
set(CMAKE_JOB_POOL_COMPILE seoul_compile)
set(CMAKE_JOB_POOL_LINK seoul_link)

add_compile_definitions(MELONDS_GL_HEADER=<GLES3/gl32.h>)
add_compile_definitions(EGL_EGLEXT_PROTOTYPES)

set(CORE-LIB ../melonDS-android-lib)
add_subdirectory(${CORE-LIB} ./melonDS-android-lib)
include(cmake/SeoulAndroidDependencies.cmake)
include_directories(${CORE-LIB}/src/android)

add_library(
        melonDS-android-frontend

        SHARED

        src/main/cpp/AndroidMelonEventMessenger.cpp
        src/main/cpp/EmulatorMessageQueueJNI.cpp
        src/main/cpp/MelonDSAndroidJNI.cpp
        src/main/cpp/MelonDSAndroidConfiguration.cpp
        src/main/cpp/MelonDSAndroidInterface.cpp
        src/main/cpp/MelonDSNandJNI.cpp
        src/main/cpp/NativeGlContext.cpp
        src/main/cpp/UriFileHandler.cpp
        src/main/cpp/JniEnvHandler.cpp
        src/main/cpp/MelonDSAndroidCameraHandler.cpp
        src/main/cpp/RetroAchievementsMapper.cpp
        src/main/cpp/RomIconBuilder.cpp
        src/main/cpp/performancehint/NdkPerformanceHintManager.cpp
        src/main/cpp/performancehint/JniPerformanceHintManager.cpp
        src/main/cpp/performancehint/PerformanceHintManagerFactory.cpp
        src/main/cpp/performancehint/ThreadSafePerformanceHintSession.cpp
)

target_link_libraries(melonDS-android-frontend melonDS-lib)
