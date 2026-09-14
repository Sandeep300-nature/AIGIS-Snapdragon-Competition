package com.aigis.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the AIGIS Spring Boot Backend service.
 *
 * @SpringBootApplication encapsulates:
 * - @Configuration: Tags the class as a source of bean definitions.
 * - @EnableAutoConfiguration: Tells Spring Boot to start adding beans based on classpath settings.
 * - @ComponentScan: Tells Spring to look for components, configurations, and services in the 'com.aigis.backend' package.
 */
@SpringBootApplication
public class AigisBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(AigisBackendApplication.class, args);
    }
}
