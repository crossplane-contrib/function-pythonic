FROM python:3.14-slim-trixie AS image

COPY dist/*.whl /root
WORKDIR /
RUN \
  set -eux && \
  pip install --upgrade pip setuptools && \
  pip install --root-user-action ignore --no-build-isolation $(echo /root/*.whl)[packages,pip-install] && \
  rm -rf /root/*.whl /root/.cache && \
  groupadd --gid 2000 pythonic && \
  useradd --uid 2000 --gid pythonic --home-dir /opt/pythonic --create-home --shell /usr/sbin/nologin pythonic && \
  mkdir --parents /opt/pythonic/.local/lib/python3.13/site-packages && \
  chown pythonic:pythonic --recursive /opt/pythonic/.local

USER pythonic:pythonic
WORKDIR /opt/pythonic
EXPOSE 9443
ENTRYPOINT ["function-pythonic"]
