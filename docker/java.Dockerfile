# syntax=docker/dockerfile:1.7
FROM maven:3.9.9-eclipse-temurin-17 AS build

WORKDIR /workspace
COPY java-app/pom.xml java-app/pom.xml
COPY java-app/src java-app/src
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp -f java-app/pom.xml -DskipTests package

FROM eclipse-temurin:17-jre-jammy

RUN groupadd --system --gid 10001 livestock \
    && useradd --system --uid 10001 --gid livestock --home-dir /opt/livestock livestock
WORKDIR /opt/livestock
COPY --from=build /workspace/java-app/target/livestock-business-service-0.1.0-SNAPSHOT.jar app.jar
USER livestock
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/livestock/app.jar"]
