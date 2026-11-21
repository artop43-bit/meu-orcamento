# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM maven:3.9.11-eclipse-temurin-21 AS maven
FROM --platform=$BUILDPLATFORM eclipse-temurin:25-jdk-noble AS java-build
COPY --from=maven /usr/share/maven /opt/maven
ENV PATH=/opt/maven/bin:$PATH
WORKDIR /src

FROM java-build AS regular-build
ADD https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git#f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4 .
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    mkdir -p calculadora/db && mvn -B -ntp flyway:migrate -Dflyway.configFiles=flyway/flyway-pro.conf
RUN --mount=type=cache,target=/root/.m2,sharing=locked mvn -B -ntp -DskipTests package

FROM java-build AS simples-build
ADD https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional.git#a926d5a76095ac0295a6612a9a54db7ffead2396 .
RUN --mount=type=cache,target=/root/.m2,sharing=locked mvn -B -ntp -DskipTests package

FROM eclipse-temurin:25-jre-noble AS runtime
WORKDIR /app
RUN install -d -m 0755 /app/calculadora/db
COPY --from=regular-build --chmod=444 /src/calculadora/db/calculadora-pro.db ./calculadora/db/
ENV SPRING_PROFILES_ACTIVE=offline \
    SPRINGDOC_API_DOCS_ENABLED=false \
    SPRINGDOC_SWAGGER_UI_ENABLED=false \
    MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED=false \
    MANAGEMENT_TRACING_ENABLED=false \
    JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=45.0 -XX:+ExitOnOutOfMemoryError"
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/motor.jar"]

FROM runtime AS regular
COPY --from=regular-build /src/target/api-regime-geral.jar ./motor.jar
COPY --from=regular-build /src/LICENSE ./LICENSE.receita-federal
EXPOSE 8080

FROM runtime AS simples
COPY --from=simples-build /src/target/api-simples-nacional.jar ./motor.jar
COPY --from=simples-build /src/LICENSE ./LICENSE.receita-federal
EXPOSE 8082
