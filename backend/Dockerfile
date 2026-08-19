# syntax=docker/dockerfile:1

FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace

COPY gradlew .
COPY gradle gradle
COPY build.gradle* settings.gradle* ./

RUN chmod +x gradlew

COPY src src

RUN ./gradlew clean bootJar --no-daemon

RUN set -eux;     JAR_FILE="$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' | head -n 1)";     test -n "$JAR_FILE";     cp "$JAR_FILE" /workspace/app.jar

FROM eclipse-temurin:21-jre AS runtime

WORKDIR /app

RUN groupadd --system spring     && useradd --system --gid spring spring

COPY --from=build --chown=spring:spring /workspace/app.jar /app/app.jar

USER spring:spring

EXPOSE 8080

ENV JAVA_OPTS=""

ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]
