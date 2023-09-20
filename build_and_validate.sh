#!/bin/bash

set -e
td="$(cd $(dirname $0) && pwd)"
echo "Activating Python venv."
source "$td/work/venv/bin/activate"

cd $td/work/iree

cmake -G Ninja -B ../iree-build/ -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -DIREE_ENABLE_ASAN=ON \
    -DIREE_BYTECODE_MODULE_ENABLE_ASAN=ON \
    -DIREE_BUILD_PYTHON_BINDINGS=ON \
    -DIREE_BYTECODE_MODULE_FORCE_LLVM_SYSTEM_LINKER=ON \
    -DPython3_EXECUTABLE=$td/work/venv/bin/python \
    -DIREE_ENABLE_ASSERTIONS=ON \
    -DIREE_ENABLE_SPLIT_DWARF=ON \
    -DIREE_ENABLE_THIN_ARCHIVES=ON \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DIREE_ENABLE_LLD=ON \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache

cd $td/work/iree-build
echo "Building all..."
ninja all
echo "Building test deps..."
ninja -j 20 iree-test-deps
