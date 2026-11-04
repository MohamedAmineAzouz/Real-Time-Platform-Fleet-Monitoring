FROM maven:3.9-eclipse-temurin-17-alpine AS deps

COPY pom.xml /build/pom.xml

RUN mvn -f /build/pom.xml \
    dependency:copy-dependencies \
    -DoutputDirectory=/deps \
    -DincludeScope=runtime \
    --no-transfer-progress

FROM flyway/flyway:10-alpine

COPY --from=deps /deps /flyway/drivers

RUN printf '#!/bin/sh\necho "Waiting for Cassandra..."\nsleep 20\nexec flyway "$@"\n' \
    > /flyway/wait-and-migrate.sh && chmod +x /flyway/wait-and-migrate.sh
    
ENTRYPOINT ["/flyway/wait-and-migrate.sh"]
CMD ["migrate"]