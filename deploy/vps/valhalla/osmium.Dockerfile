# One-off tool image for update.sh: cuts the Astana extract out of the Kazakhstan file (osmium extract).
# Not a service: it is run with --rm and thrown away; only this recipe is kept.
FROM ubuntu:24.04
RUN apt-get update \
    && apt-get install -y --no-install-recommends osmium-tool \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["osmium"]
