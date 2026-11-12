FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS source
RUN git --version
ARG UPSTREAM_REPOSITORY=https://github.com/github/github-mcp-server.git
ARG UPSTREAM_VERSION=v2.0.3
ARG UPSTREAM_COMMIT=b98d115bbb080e9555466a96656ec4df605aea21
WORKDIR /src
RUN git init . \
    && git remote add origin "${UPSTREAM_REPOSITORY}" \
    && git fetch --depth 1 origin "refs/tags/${UPSTREAM_VERSION}:refs/tags/${UPSTREAM_VERSION}" \
    && git checkout --detach "${UPSTREAM_COMMIT}" \
    && test "$(git rev-parse HEAD)" = "${UPSTREAM_COMMIT}"
COPY acmm_governor.go /src/pkg/http/transport/acmm_governor.go
RUN test "$(grep -c 'Transport: http.DefaultTransport,' pkg/github/dependencies.go)" -eq 2 \
    && sed -i 's/Transport: http.DefaultTransport,/Transport: transport.NewACMMGovernedTransport(http.DefaultTransport),/g' pkg/github/dependencies.go \
    && test "$(grep -c 'transport.NewACMMGovernedTransport(http.DefaultTransport)' pkg/github/dependencies.go)" -eq 2

FROM node:26-alpine@sha256:e88a35be04478413b7c71c455cd9865de9b9360e1f43456be5951032d7ac1a66 AS ui-build
WORKDIR /app
COPY --from=source /src/ui/package*.json ./ui/
RUN cd ui && npm ci
COPY --from=source /src/ui/ ./ui/
COPY --from=source /src/pkg/github/ui_dist/ ./pkg/github/ui_dist/
RUN mkdir -p ./pkg/github/ui_dist && cd ui && npm run build

FROM golang:1.27.3-alpine@sha256:f2c872bcee949b7be9c490efd02b48a8a2fbf947cdf533f1c58525ec9d8170fd AS build
ARG UPSTREAM_VERSION=v2.0.3
ARG UPSTREAM_COMMIT=b98d115bbb080e9555466a96656ec4df605aea21
ARG GOVERNOR_VERSION=v1
WORKDIR /build
COPY --from=source /src/ .
COPY --from=ui-build /app/pkg/github/ui_dist/* ./pkg/github/ui_dist/
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build \
    -ldflags="-s -w -X main.version=${UPSTREAM_VERSION}-acmm-governed-${GOVERNOR_VERSION} -X main.commit=${UPSTREAM_COMMIT} -X main.date=2026-10-21T09:52:00Z" \
    -o /bin/github-mcp-server ./cmd/github-mcp-server

FROM gcr.io/distroless/base-debian12@sha256:fabbf1c0c357a3d42550111351daed089b20a2c954df13ee2fcff60602515e84
ARG UPSTREAM_VERSION=v2.0.3
ARG UPSTREAM_COMMIT=b98d115bbb080e9555466a96656ec4df605aea21
ARG GOVERNOR_VERSION=v1
LABEL io.modelcontextprotocol.server.name="io.github.github/github-mcp-server" \
      io.acmm.github-mcp.upstream-version="${UPSTREAM_VERSION}" \
      io.acmm.github-mcp.upstream-commit="${UPSTREAM_COMMIT}" \
      io.acmm.github-mcp.governor-version="${GOVERNOR_VERSION}"
WORKDIR /server
COPY --from=build /bin/github-mcp-server .
EXPOSE 8082
ENTRYPOINT ["/server/github-mcp-server"]
CMD ["stdio"]
