# OpenFOAM v2412 (ESI/OpenCFD) + the project's Python stack, pinned.
FROM opencfd/openfoam-default:2412

USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git zstd \
      libgl1 libglu1-mesa libegl1 libopengl0 libgomp1 libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/*

# Python 3.13 via uv: the version docker/requirements.lock was resolved and tested with
# (some locked packages need >= 3.12; the base image's python3 is older).
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
 && uv python install 3.13 \
 && uv venv -p 3.13 /opt/venv
COPY docker/requirements.lock /tmp/requirements.lock
RUN uv pip install --python /opt/venv/bin/python --no-cache -r /tmp/requirements.lock

ENV PATH=/opt/venv/bin:$PATH \
    FOAM_BASHRC=/usr/lib/openfoam/openfoam2412/etc/bashrc \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
    OMPI_MCA_rmaps_base_oversubscribe=1 \
    OMPI_MCA_hwloc_base_use_hwthreads_as_cpus=1 \
    PYTHONUNBUFFERED=1

# Smoke test at build time: both stacks load.
RUN bash -c "source $FOAM_BASHRC && simpleFoam -help >/dev/null && snappyHexMesh -help >/dev/null" \
 && python -c "import numpy, scipy, trimesh, manifold3d, pymeshlab, sklearn, pyamg; print('python ok')"
