FROM maven:3.9-eclipse-temurin-17-alpine AS deps

# Create a minimal POM to resolve cassandra-jdbc-wrapper + ALL transitive deps
RUN mkdir -p /build && cat > /build/pom.xml << 'EOF'
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>flyway.deps</groupId>
  <artifactId>cassandra-driver-deps</artifactId>
  <version>1.0</version>
  <dependencies>
    <dependency>
      <groupId>com.ing.data</groupId>
      <artifactId>cassandra-jdbc-wrapper</artifactId>
      <version>4.11.1</version>
    </dependency>
  </dependencies>
</project>
EOF

# Copy ALL transitive jars into /deps (flat directory)
RUN mvn -f /build/pom.xml \
    dependency:copy-dependencies \
    -DoutputDirectory=/deps \
    -DincludeScope=runtime \
    --no-transfer-progress

# ── Final image ───────────────────────────────────────────────────────────────
FROM flyway/flyway:10-alpine

# Copy every resolved jar (cassandra driver + netty + caffeine + etc.)
COPY --from=deps /deps /flyway/drivers

# Wait wrapper
RUN printf '#!/bin/sh\necho "Waiting for Cassandra..."\nsleep 20\nexec flyway "$@"\n' \
    > /flyway/wait-and-migrate.sh && chmod +x /flyway/wait-and-migrate.sh
    
ENTRYPOINT ["/flyway/wait-and-migrate.sh"]
CMD ["migrate"]