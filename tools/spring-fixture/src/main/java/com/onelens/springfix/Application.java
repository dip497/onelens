package com.onelens.springfix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Minimal Spring Boot entrypoint. The headless export should surface this as
 * a Spring application node (apps) and a CONFIGURATION/COMPONENT bean.
 */
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
