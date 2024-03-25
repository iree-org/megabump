#!/bin/bash

set -e
td="$(cd $(dirname $0) && pwd)"
echo "Activating Python venv."

# Linux venv
# source "$td/../work/venv/bin/activate"

# Windows venv
$td/../work/venv/Scripts/activate.bat

cd $td/../work/iree

# Use absolute paths to avoid problems with symlinked iree repo

# Linux build.
# cmake -G Ninja -B $td/../work/iree-build -S . \
#     -DCMAKE_BUILD_TYPE=Release \
#     -DIREE_ENABLE_ASAN=ON \
#     -DIREE_BUILD_PYTHON_BINDINGS=ON \
#     -DPython3_EXECUTABLE=$td/../work/venv/bin/python \
#     -DIREE_ENABLE_ASSERTIONS=ON \
#     -DIREE_ENABLE_SPLIT_DWARF=ON \
#     -DIREE_ENABLE_THIN_ARCHIVES=ON \
#     -DCMAKE_C_COMPILER=clang \
#     -DCMAKE_CXX_COMPILER=clang++ \
#     -DIREE_ENABLE_LLD=ON \
#     -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

# Windows build.
cmake -G Ninja -B $td/../work/iree-build -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -DIREE_BUILD_PYTHON_BINDINGS=ON \
    -DPython3_EXECUTABLE=$td/../work/venv/Scripts/python.exe \
    -DIREE_ENABLE_ASSERTIONS=ON \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

cd $td/../work/iree-build
echo "Building all..."
ninja all
echo "Building test deps..."
ninja iree-test-deps
